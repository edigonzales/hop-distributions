import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.apache.hop.core.HopEnvironment;
import org.apache.hop.core.variables.Variables;
import org.apache.hop.metadata.serializer.memory.MemoryMetadataProvider;
import org.apache.hop.pipeline.PipelineMeta;
import org.apache.hop.pipeline.config.PipelineRunConfiguration;
import org.apache.hop.pipeline.engines.local.*;

/** Compiled against the host; SDMX classes are loaded exclusively from the installed ZIP. */
public class SdmxCancellationProbe {
  public static void main(String[] args) throws Exception {
    Path repo = Path.of(args[0]);
    Path work = Path.of(args[1]);
    byte[] structure = Files.readAllBytes(repo.resolve("sdmx/structure.json"));
    var lines = Files.readAllLines(repo.resolve("sdmx/observations.csv"));
    HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
    CountDownLatch streaming = new CountDownLatch(1);
    AtomicInteger dataRequests = new AtomicInteger();
    server.createContext(
        "/rest/dataflow",
        e -> {
          e.getResponseHeaders().set("Content-Type", "application/vnd.sdmx.structure+json");
          e.sendResponseHeaders(200, structure.length);
          e.getResponseBody().write(structure);
          e.close();
        });
    server.createContext(
        "/rest/data",
        e -> {
          dataRequests.incrementAndGet();
          e.getResponseHeaders().set("Content-Type", "application/vnd.sdmx.data+csv;version=2");
          e.sendResponseHeaders(200, 0);
          try {
            e.getResponseBody().write((lines.get(0) + "\n").getBytes(StandardCharsets.UTF_8));
            for (int i = 0; i < 1000; i++) {
              e.getResponseBody().write((lines.get(1) + "\n").getBytes(StandardCharsets.UTF_8));
              e.getResponseBody().flush();
              streaming.countDown();
              Thread.sleep(30);
            }
          } catch (Exception ignored) {
          } finally {
            e.close();
          }
        });
    server.start();
    try {
      HopEnvironment.init();
      Variables vars = new Variables();
      var provider = new MemoryMetadataProvider();
      PipelineMeta pm =
          new PipelineMeta(
              repo.resolve("sdmx/health-financing.hpl").toString(),
              provider,
              vars);
      String location =
          pm.findTransform("SDMX Input")
              .getTransform()
              .getClass()
              .getProtectionDomain()
              .getCodeSource()
              .getLocation()
              .toString();
      if (!location.contains("plugins/transforms/hop-sdmx/"))
        throw new AssertionError("Not testing installed plugin: " + location);
      var config = new PipelineRunConfiguration();
      config.setName("test");
      var local = new LocalPipelineRunConfiguration();
      local.setEnginePluginId("Local");
      config.setEngineRunConfiguration(local);
      provider.getSerializer(PipelineRunConfiguration.class).save(config);
      var engine =
          org.apache.hop.pipeline.engine.PipelineEngineFactory.createPipelineEngine(
              vars, "test", provider, pm);
      engine.setParameterValue(
          "SDMX_ENDPOINT", "http://127.0.0.1:" + server.getAddress().getPort() + "/rest");
      engine.setParameterValue("START_PERIOD", "2023");
      engine.setParameterValue("END_PERIOD", "2023");
      engine.setParameterValue("OUTPUT_FILE", work.resolve("cancelled").toString());
      engine.activateParameters(engine);
      engine.prepareExecution();
      engine.startThreads();
      if (!streaming.await(10, TimeUnit.SECONDS))
        throw new AssertionError("Data stream not opened");
      try (var executor = Executors.newSingleThreadExecutor()) {
        Future<?> stopped =
            executor.submit(
                () -> {
                  engine.stopAll();
                  engine.waitUntilFinished();
                });
        stopped.get(10, TimeUnit.SECONDS);
      }
      if (dataRequests.get() != 1)
        throw new AssertionError("Cancellation replayed the data request");
      System.out.println("Installed pipeline cancellation passed (one data request)");
    } finally {
      server.stop(0);
    }
  }
}
