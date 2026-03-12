package com.anylogic.alpyne.json;

import com.anylogic.engine.analysis.DataSet;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.SerializerProvider;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

public class DataSetSerializer extends ACustomSerializer<DataSet> {
   public DataSetSerializer() {
      super(DataSet.class);
   }

   public void serialize(DataSet value, JsonGenerator jgen, SerializerProvider provider) throws IOException, JsonProcessingException {
      jgen.writeStartObject();
      jgen.writeNumberField("xmin", value.getXMin());
      jgen.writeNumberField("xmean", value.getXMean());
      jgen.writeNumberField("xmedian", value.getXMedian());
      jgen.writeNumberField("xmax", value.getXMax());
      jgen.writeNumberField("ymin", value.getYMin());
      jgen.writeNumberField("ymean", value.getYMean());
      jgen.writeNumberField("ymedian", value.getYMedian());
      jgen.writeNumberField("ymax", value.getYMax());
      List<double[]> values = new ArrayList<>();
      IntStream.range(0, value.size()).forEach(i -> values.add(new double[]{value.getX(i), value.getY(i)}));
      jgen.writeObjectField("plainDataTable", value.getPlainDataTable());
      jgen.writeEndObject();
   }
}
