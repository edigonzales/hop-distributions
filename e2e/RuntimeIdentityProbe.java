import org.apache.hop.core.HopEnvironment;
import org.apache.hop.core.plugins.*;
import org.apache.hop.core.row.value.ValueMetaPluginType;
public class RuntimeIdentityProbe {
 public static void main(String[] args) throws Exception {
  HopEnvironment.init();
  PluginRegistry r=PluginRegistry.getInstance();
  IPlugin raster=r.findPluginWithId(TransformPluginType.class,"SOGIS_RASTER_CLIP");
  IPlugin geometry=r.findPluginWithId(ValueMetaPluginType.class,"43663879");
  ClassLoader first=r.getClassLoader(args[0].equals("raster-first")?raster:geometry);
  ClassLoader a=r.getClassLoader(raster), b=r.getClassLoader(geometry);
  if(a!=b) throw new AssertionError("Different classloaders");
  for(String n:new String[]{"org.locationtech.jts.geom.GeometryFactory","com.atolcd.hop.core.row.value.ValueMetaGeometry"}) {
   Class<?> ca=a.loadClass(n),cb=b.loadClass(n);
   if(ca!=cb) throw new AssertionError("Different classes "+n);
   java.nio.file.Path origin=java.nio.file.Path.of(ca.getProtectionDomain().getCodeSource().getLocation().toURI()).toRealPath();
   java.nio.file.Path central=java.nio.file.Path.of("plugins/misc/hop-geometry-type").toRealPath();
   if(!origin.startsWith(central)) throw new AssertionError("Runtime outside central Geometry plugin: "+origin);
   System.out.println("IDENTITY OK "+args[0]+" "+n+" "+ca.getProtectionDomain().getCodeSource().getLocation());
  }
 }
}
