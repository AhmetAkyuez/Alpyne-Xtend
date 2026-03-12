package com.anylogic.alpyne.json;

import com.anylogic.engine.analysis.Histogram2DData;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.SerializerProvider;
import java.io.IOException;

public class Histogram2DSerializer extends ACustomSerializer<Histogram2DData> {
   public Histogram2DSerializer() {
      super(Histogram2DData.class);
   }

   public void serialize(Histogram2DData value, JsonGenerator jgen, SerializerProvider provider) throws IOException, JsonProcessingException {
      jgen.writeStartObject();
      int nX = value.getNumberOfXIntervals();
      int nY = value.getNumberOfYIntervals();
      int[][] hits = new int[nY][nX];
      int[] hitsOutLow = new int[nX];
      int[] hitsOutHigh = new int[nX];

      for (int x = 0; x < nX; x++) {
         int xcount = value.count(x);
         hitsOutLow[x] = Math.round((float)value.getPDFOutsideLow(x) * xcount);
         hitsOutHigh[x] = Math.round((float)value.getPDFOutsideHigh(x) * xcount);

         for (int y = 0; y < nY; y++) {
            hits[y][x] = Math.round((float)value.getPDF(x, y) * xcount);
         }
      }

      jgen.writeObjectField("hits", hits);
      jgen.writeObjectField("hitsOutLow", hitsOutLow);
      jgen.writeObjectField("hitsOutHigh", hitsOutHigh);
      jgen.writeNumberField("xMin", value.getXMin());
      jgen.writeNumberField("xMax", value.getXMax());
      jgen.writeNumberField("yMin", value.getYMin());
      jgen.writeNumberField("yMax", value.getYMax());
      jgen.writeEndObject();
   }
}
