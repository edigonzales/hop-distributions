import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.function.BooleanSupplier;
import org.apache.hop.core.Const;
import org.apache.hop.core.HopEnvironment;
import org.apache.hop.core.config.HopConfig;
import org.apache.hop.core.gui.plugin.GuiPluginType;
import org.apache.hop.core.plugins.PluginRegistry;
import org.apache.hop.ui.hopgui.HopGuiEnvironment;
import org.apache.hop.ui.hopgui.perspective.HopPerspectivePluginType;
import org.apache.hop.ui.hopgui.perspective.IHopPerspective;
import org.eclipse.swt.SWT;
import org.eclipse.swt.custom.StyledText;
import org.eclipse.swt.graphics.GC;
import org.eclipse.swt.graphics.Image;
import org.eclipse.swt.graphics.ImageLoader;
import org.eclipse.swt.layout.FormLayout;
import org.eclipse.swt.widgets.Button;
import org.eclipse.swt.widgets.Composite;
import org.eclipse.swt.widgets.Control;
import org.eclipse.swt.widgets.Display;
import org.eclipse.swt.widgets.Event;
import org.eclipse.swt.widgets.Shell;
import org.eclipse.swt.widgets.Text;
import org.eclipse.swt.widgets.Tree;
import org.eclipse.swt.widgets.TreeItem;

/** Exercises the installed perspective and its engines without a launcher on the JVM classpath. */
public class ApplicationLauncherProbe {
  public static void main(String[] args) throws Exception {
    Path source = Path.of(args[0]).toRealPath();
    Path work = Path.of(args[1]).toAbsolutePath();
    String revision = args[2];
    Path config = work.resolve("config");
    Files.createDirectories(config);
    Files.writeString(config.resolve("hop-config.json"), "{}");
    System.setProperty("HOP_CONFIG_FOLDER", config.toString());
    System.setProperty("HOP_AUDIT_FOLDER", work.resolve("audit").toString());
    System.setProperty("HOP_METADATA_FOLDER", config.resolve("metadata").toString());
    try {
      Class.forName("ch.so.agi.hop.launcher.LauncherPerspective");
      throw new AssertionError("Launcher must only be available through its installed classloader");
    } catch (ClassNotFoundException expected) {
      // This probe is compiled and run with only Hop host libraries and the native SWT JAR.
    }
    HopEnvironment.init();
    HopGuiEnvironment.init(
        List.of(GuiPluginType.getInstance(), HopPerspectivePluginType.getInstance()));
    var registry = PluginRegistry.getInstance();
    var plugin = registry.findPluginWithId(HopPerspectivePluginType.class, "application-launcher");
    require(plugin != null, "Missing application-launcher perspective");
    // Resolve before requesting the loader, exactly as HopGui.loadPerspectives() does.
    Class<IHopPerspective> perspectiveType = registry.getClass(plugin, IHopPerspective.class);
    require(perspectiveType.getClassLoader() == registry.getClassLoader(plugin),
        "Perspective must come from the installed plugin classloader");
    HopConfig.saveOptions(Map.of(
        "applicationLauncher.repository", source.toString(),
        "applicationLauncher.branch", "main",
        "applicationLauncher.checkout", work.resolve("checkout").toString()));
    Path input = work.resolve("Eingabe ä ; test.xml");
    Path output = work.resolve("Ausgabe ä");
    Files.writeString(input, "<demo/>\n");
    Files.createDirectories(output);
    Path runs = Path.of(Const.HOP_CONFIG_FOLDER).resolve("application-launcher/runs");
    Display display = new Display();
    Shell shell = new Shell(display);
    shell.setText("Distribution Application Launcher E2E");
    shell.setLayout(new FormLayout());
    shell.setSize(1100, 720);
    try {
      IHopPerspective perspective = perspectiveType.getConstructor().newInstance();
      require("application-launcher".equals(perspective.getId()), "Wrong perspective ID");
      perspective.initialize(null, shell);
      shell.open();
      perspective.perspectiveActivated();
      Composite content = (Composite) perspective.getControl();
      waitUi(display, () -> button(content, "Start").getEnabled(), content);
      require(Files.isDirectory(work.resolve("checkout/.git")), "Local repository was not cloned");
      Tree tree = (Tree) marked(content, "launcher.apps", Boolean.TRUE);
      require(applications(tree.getItems()).size() == 2, "Expected pipeline and workflow catalog");
      for (String id : List.of("demo.hello-world", "demo.workflow")) {
        select(content, id);
        fill(content, "INPUT_XML", input.toString());
        fill(content, "OUTPUT_DIR", output.toString());
        // A sentinel also proves that each run replaces the previous output.
        Files.writeString(output.resolve("hello-world.csv"), "MUST BE REPLACED\n");
        int before = reports(runs).size();
        button(content, "Start").notifyListeners(SWT.Selection, new Event());
        require(!button(content, "Start").getEnabled(), "Run did not enter busy state");
        waitUi(display, () -> button(content, "Start").getEnabled(), content);
        checkCsv(output, input);
        checkReport(runs, before, id, "SUCCESS", revision);
        require(log(content).contains(id + ": SUCCESS"), "Missing success in native log");
        require(log(content).contains("Write CSV"), "Missing pipeline/child log");
        require(button(content, "OpenOutput").getEnabled(), "Output action must be enabled");
        System.out.println("Launcher UI execution OK: " + id);
      }
      select(content, "demo.hello-world");
      fill(content, "INPUT_XML", work.resolve("missing.xml").toString());
      fill(content, "OUTPUT_DIR", output.toString());
      Files.delete(output.resolve("hello-world.csv"));
      int before = reports(runs).size();
      button(content, "Start").notifyListeners(SWT.Selection, new Event());
      waitUi(display, () -> button(content, "Start").getEnabled(), content);
      checkReport(runs, before, "demo.hello-world", "FAILED", revision);
      require(!Files.exists(output.resolve("hello-world.csv")), "Invalid input executed the pipeline");
      require(log(content).contains("demo.hello-world: FAILED"), "Missing failure in native log");
      require(!button(content, "OpenOutput").getEnabled(), "Invalid input enabled output action");
      screenshot(shell, work.resolve("launcher.png"));
      System.out.println("Launcher missing-input failure OK");
    } finally {
      shell.dispose();
      display.dispose();
    }
    require(System.getProperty("PROJECT_HOME") == null, "Launcher changed the active Hop project");
    System.out.println("Application Launcher distribution E2E passed");
  }

  private static List<Path> reports(Path runs) throws Exception {
    if (!Files.exists(runs)) return List.of();
    try (var files = Files.walk(runs)) {
      return files.filter(p -> p.getFileName().toString().equals("run.properties")).toList();
    }
  }

  private static void checkReport(
      Path runs, int before, String application, String status, String revision) throws Exception {
    List<Path> reports = reports(runs);
    require(reports.size() == before + 1, "Expected exactly one new run report");
    int matching = 0;
    for (Path report : reports) {
      Properties values = new Properties();
      try (var reader = Files.newBufferedReader(report)) {
        values.load(reader);
      }
      if (!application.equals(values.getProperty("application"))
          || !status.equals(values.getProperty("status"))) continue;
      matching++;
      require(revision.equals(values.getProperty("revision")), "Wrong run revision: " + values);
      require(!values.getProperty("start", "").isBlank()
          && !values.getProperty("end", "").isBlank(), "Missing run timestamps");
      String log = Files.readString(report.resolveSibling("hop.log"));
      require(log.contains(application + ": " + status), "Missing persisted status");
      if (status.equals("SUCCESS")) {
        require(values.getProperty("error", "").isEmpty(), "Successful run has an error");
        require(log.contains("Write CSV"), "Missing persisted engine log");
      } else {
        require(values.getProperty("error", "").contains("missing.xml"),
            "Missing input must be reported: " + values);
      }
    }
    require(matching == 1, "Missing or duplicate matching report for " + application + ": " + status);
  }

  private static void checkCsv(Path output, Path input) throws Exception {
    String value = input.toRealPath().toString();
    if (value.contains(";") || value.contains("\""))
      value = "\"" + value.replace("\"", "\"\"") + "\"";
    require(Files.readAllLines(output.resolve("hello-world.csv"))
        .equals(List.of("message;input_file", "Hello World;" + value)),
        "Wrong CSV output or forwarded input parameter");
  }

  private static void waitUi(Display display, BooleanSupplier done, Composite content)
      throws Exception {
    long deadline = System.nanoTime() + Duration.ofSeconds(30).toNanos();
    while (!done.getAsBoolean()) {
      require(System.nanoTime() < deadline, "Launcher UI timed out:\n" + log(content));
      if (!display.readAndDispatch()) Thread.sleep(10);
    }
    while (display.readAndDispatch()) {}
  }

  private static List<Control> controls(Composite root) {
    List<Control> result = new ArrayList<>();
    for (Control control : root.getChildren()) {
      result.add(control);
      if (control instanceof Composite nested) result.addAll(controls(nested));
    }
    return result;
  }

  private static Control marked(Composite content, String key, Object value) {
    return controls(content).stream().filter(c -> value.equals(c.getData(key)))
        .findFirst().orElseThrow(() -> new AssertionError("Missing control: " + key + "=" + value));
  }

  private static Button button(Composite content, String key) {
    return (Button) marked(content, "launcher.action", key);
  }

  private static void fill(Composite content, String parameter, String value) {
    ((Text) marked(content, "launcher.parameter", parameter)).setText(value);
  }

  private static List<TreeItem> applications(TreeItem[] items) {
    List<TreeItem> result = new ArrayList<>();
    for (TreeItem item : items) {
      if (item.getData("launcher.applicationId") != null) result.add(item);
      result.addAll(applications(item.getItems()));
    }
    return result;
  }

  private static void select(Composite content, String id) {
    Tree tree = (Tree) marked(content, "launcher.apps", Boolean.TRUE);
    TreeItem item = applications(tree.getItems()).stream()
        .filter(i -> id.equals(i.getData("launcher.applicationId"))).findFirst().orElseThrow();
    tree.setSelection(item);
    Event event = new Event();
    event.item = item;
    tree.notifyListeners(SWT.Selection, event);
  }

  private static String log(Composite content) {
    return controls(content).stream().filter(c -> c instanceof StyledText)
        .map(c -> ((StyledText) c).getText()).findFirst().orElse("");
  }

  private static void screenshot(Shell shell, Path path) {
    Image image = new Image(shell.getDisplay(), shell.getBounds().width, shell.getBounds().height);
    GC gc = new GC(shell);
    try {
      gc.copyArea(image, 0, 0);
      ImageLoader loader = new ImageLoader();
      loader.data = new org.eclipse.swt.graphics.ImageData[] {image.getImageData()};
      loader.save(path.toString(), SWT.IMAGE_PNG);
    } finally {
      gc.dispose();
      image.dispose();
    }
  }

  private static void require(boolean condition, String message) {
    if (!condition) throw new AssertionError(message);
  }
}
