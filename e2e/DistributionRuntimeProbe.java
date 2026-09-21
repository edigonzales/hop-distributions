import java.io.*;
import java.nio.file.*;
import org.apache.hop.core.HopEnvironment;
import org.apache.hop.core.plugins.*;
import org.apache.hop.core.gui.plugin.GuiPluginType;
import org.apache.hop.core.row.IValueMeta;
import org.apache.hop.core.row.value.ValueMetaPluginType;
import org.apache.hop.core.row.value.ValueMetaString;

/** Runtime assertions using only Hop's plugin loaders, never Maven's classpath. */
public class DistributionRuntimeProbe {
  public static void main(String[] args) throws Exception {
    HopEnvironment.init();
    var registry = PluginRegistry.getInstance();
    String[] transforms = {"SOGIS_VECTOR_READER", "SOGIS_VECTOR_WRITER", "SOGIS_RASTER_READER",
      "SOGIS_RASTER_VALUE_CLIP", "SOGIS_RASTER_VALUE_REPROJECT",
      "SOGIS_RASTER_VALUE_ZONAL_STATS", "SOGIS_RASTER_WRITER", "GEOMETRY_CALCULATOR_TRANSFORM",
      "JSON_OBJECT_BUILDER", "JSON_ARRAY_BUILDER",
      "INTERLIS_INPUT", "INTERLIS_OUTPUT", "INTERLIS_ILI2DB_TRANSFORM",
      "INTERLIS_ILIVALIDATOR_TRANSFORM", "GraalPyTransform"};
    for (String id : transforms) {
      var plugin=registry.findPluginWithId(TransformPluginType.class,id);
      if(plugin==null) throw new AssertionError("Missing transform "+id);
      var loader=registry.getClassLoader(plugin);
      for(String name:plugin.getClassMap().values()) loader.loadClass(name);
      System.out.println("Registered and loadable: "+id);
    }
    for(String id:new String[]{"INTERLIS_ILI2DB_ACTION","INTERLIS_ILIVALIDATOR_ACTION"}) {
      var plugin=registry.findPluginWithId(ActionPluginType.class,id);
      if(plugin==null) throw new AssertionError("Missing action "+id);
      for(String name:plugin.getClassMap().values()) registry.getClassLoader(plugin).loadClass(name);
    }
    var geometryPlugin=registry.findPluginWithId(ValueMetaPluginType.class,"43663879");
    var loader=registry.getClassLoader(geometryPlugin);
    var meta=(IValueMeta)loader.loadClass("com.atolcd.hop.core.row.value.ValueMetaGeometry")
        .getConstructor(String.class).newInstance("geometry");
    for(String wkt:new String[]{"POINT (1 2)","POINT Z (1 2 3)","POINT M (1 2 4)",
        "POINT ZM (1 2 3 4)","CIRCULARSTRING (0 0, 1 1, 2 0)",
        "CURVEPOLYGON (CIRCULARSTRING (0 0, 1 1, 2 0, 1 -1, 0 0))"}) {
      Object value;
      if(wkt.startsWith("CIRCULARSTRING") || wkt.startsWith("CURVEPOLYGON")) {
        var ring=java.nio.ByteBuffer.allocate(1+4+4+5*16).order(java.nio.ByteOrder.LITTLE_ENDIAN);
        ring.put((byte)1).putInt(8).putInt(5);
        for(double coordinate:new double[]{0,0,1,1,2,0,1,-1,0,0}) ring.putDouble(coordinate);
        byte[] wkb=ring.array();
        if(wkt.startsWith("CURVEPOLYGON")) {
          var polygon=java.nio.ByteBuffer.allocate(9+wkb.length).order(java.nio.ByteOrder.LITTLE_ENDIAN);
          polygon.put((byte)1).putInt(10).putInt(1).put(wkb); wkb=polygon.array();
        }
        value=loader.loadClass("com.atolcd.hop.gis.geometry.curve.CurveGeometrySupport")
            .getMethod("readWkb",byte[].class).invoke(null,(Object)wkb);
        value.getClass().getMethod("setSRID",int.class).invoke(value,2056);
      } else value=meta.convertData(new ValueMetaString(),"SRID=2056;"+wkt);
      var bytes=new ByteArrayOutputStream();
      meta.writeData(new DataOutputStream(bytes),value);
      Object restored=meta.readData(new DataInputStream(new ByteArrayInputStream(bytes.toByteArray())));
      for(Object copy:new Object[]{restored,meta.cloneValueData(value)}) {
        if(!meta.getString(value).equals(meta.getString(copy))) throw new AssertionError("Geometry roundtrip: "+wkt);
        if(!copy.getClass().getMethod("getSRID").invoke(copy).equals(2056)) throw new AssertionError("Lost SRID");
      }
      System.out.println("Geometry serialization and preview OK: "+meta.getString(restored));
    }
    // Register the GUI plugin metadata after normal engine initialization, as Hop GUI does.
    PluginRegistry.addPluginType(GuiPluginType.getInstance());
    GuiPluginType.getInstance().searchPlugins();
    boolean inspector=false;
    for(var plugin:registry.getPlugins(GuiPluginType.class)) {
      for(String name:plugin.getClassMap().values()) {
        if(name.equals("ch.so.agi.hop.geometry.inspector.GeometryInspectorGuiPlugin")) {
          registry.getClassLoader(plugin).loadClass(name).getConstructor().newInstance();
          inspector=true;
        }
      }
    }
    if(!inspector) throw new AssertionError("Geometry Inspector did not initialize");
    if(org.eclipse.swt.widgets.Display.getCurrent()!=null) org.eclipse.swt.widgets.Display.getCurrent().dispose();
    System.out.println("Distribution runtime OK");
  }
}
