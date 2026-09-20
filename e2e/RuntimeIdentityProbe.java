import org.apache.hop.core.HopEnvironment;
import org.apache.hop.core.plugins.*;
import org.apache.hop.core.row.value.ValueMetaPluginType;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
public class RuntimeIdentityProbe {
 public static void main(String[] args) throws Exception {
  HopEnvironment.init();
  PluginRegistry r=PluginRegistry.getInstance();
  IPlugin raster=r.findPluginWithId(TransformPluginType.class,"SOGIS_RASTER_VALUE_CLIP");
  IPlugin geometry=r.findPluginWithId(ValueMetaPluginType.class,"43663879");
  ClassLoader first=r.getClassLoader(args[0].equals("raster-first")?raster:geometry);
  ClassLoader a=r.getClassLoader(raster), b=r.getClassLoader(geometry);
  if(a!=b) throw new AssertionError("Different classloaders");
  for(String n:new String[]{"org.locationtech.jts.geom.GeometryFactory","com.atolcd.hop.core.row.value.ValueMetaGeometry","org.geotools.ows.wmts.WebMapTileServer","org.eclipse.imagen.OperationRegistry","org.eclipse.imagen.PlanarImage"}) {
   Class<?> ca=a.loadClass(n),cb=b.loadClass(n);
   if(ca!=cb) throw new AssertionError("Different classes "+n);
   java.nio.file.Path origin=java.nio.file.Path.of(ca.getProtectionDomain().getCodeSource().getLocation().toURI()).toRealPath();
   java.nio.file.Path central=java.nio.file.Path.of("plugins/misc/hop-geometry-type").toRealPath();
   if(!origin.startsWith(central)) throw new AssertionError("Runtime outside central Geometry plugin: "+origin);
   System.out.println("IDENTITY OK "+args[0]+" "+n+" "+ca.getProtectionDomain().getCodeSource().getLocation());
  }
  Set<String> registrations=new HashSet<>();
  List<URL> resources=java.util.Collections.list(a.getResources("META-INF/registryFile.imagen"));
  if(resources.isEmpty()) throw new AssertionError("No Imagen registry resource from Geometry Type");
  for(URL resource:resources) try(BufferedReader reader=new BufferedReader(new InputStreamReader(resource.openStream(), StandardCharsets.UTF_8))) {
   String line;
   while((line=reader.readLine())!=null) {
    line=line.trim();
    if(line.isEmpty()||line.startsWith("#")) continue;
    String[] fields=line.split("\\s+");
    if((fields[0].equals("descriptor")||fields[0].equals("rendered"))&&!registrations.add(line)) throw new AssertionError("Duplicate Imagen registration "+line+" from "+resource);
   }
  }
  for(String n:new String[]{"ch.so.agi.hop.raster.RasterDataset","ch.so.agi.hop.raster.type.ValueMetaRaster"}) {
   Class<?> ca=a.loadClass(n), cb=b.loadClass(n);
   if(ca!=cb) throw new AssertionError("Different raster class identity: "+n);
   var origin=java.nio.file.Path.of(ca.getProtectionDomain().getCodeSource().getLocation().toURI()).toRealPath();
   if(!origin.startsWith(java.nio.file.Path.of("plugins/misc/hop-raster-type").toRealPath()))throw new AssertionError("Raster class outside central type plugin: "+origin);
  }
  Class<?> backend=a.loadClass("ch.so.agi.hop.raster.geotools.GeoToolsRasterBackend");
  if(backend!=b.loadClass(backend.getName())) throw new AssertionError("Different raster backend class identity");
  var backendOrigin=java.nio.file.Path.of(backend.getProtectionDomain().getCodeSource().getLocation().toURI()).toRealPath();
  if(!backendOrigin.startsWith(java.nio.file.Path.of("plugins/transforms/vector-raster/lib").toRealPath()))throw new AssertionError("Raster backend outside Vector/Raster lib: "+backendOrigin);

 }
}
