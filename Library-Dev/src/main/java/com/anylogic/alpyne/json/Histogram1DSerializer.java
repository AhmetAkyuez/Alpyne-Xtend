package com.anylogic.alpyne.json;

import com.anylogic.engine.analysis.HistogramData;
import com.anylogic.engine.analysis.HistogramSimpleData;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.SerializerProvider;
import java.io.IOException;
import java.util.HashMap;
import java.util.stream.IntStream;

public class Histogram1DSerializer extends ACustomSerializer<HistogramData> {
   public Histogram1DSerializer() {
      super(HistogramData.class);
   }

   public void serialize(HistogramData value, JsonGenerator jgen, SerializerProvider provider) throws IOException, JsonProcessingException {
      jgen.writeStartObject();
      int count = value.count();
      jgen.writeNumberField("count", count);
      jgen.writeNumberField("lowerBound", value.getXMin());
      jgen.writeNumberField("intervalWidth", value.getIntervalWidth());
      int[] hits = IntStream.range(0, value.getNumberOfIntervals()).map(i -> Math.round((float)value.getPDF(i) * count)).toArray();
      jgen.writeObjectField("hits", hits);
      if (value instanceof HistogramSimpleData hdataSimple) {
         jgen.writeNumberField("hitsOutLow", Math.round((float)hdataSimple.getPDFOutsideLow() * count));
         jgen.writeNumberField("hitsOutHigh", Math.round((float)hdataSimple.getPDFOutsideHigh() * count));
      }

      HashMap<String, Double> dtableStats = new HashMap<>();
      dtableStats.put("min", value.min());
      dtableStats.put("max", value.max());
      dtableStats.put("mean", value.mean());
      dtableStats.put("deviation", value.deviation());
      jgen.writeObjectField("statistics", dtableStats);
      jgen.writeEndObject();
   }
}
