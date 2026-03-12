package com.anylogic.alpyne.json;

import com.anylogic.engine.analysis.StatisticsContinuous;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.SerializerProvider;
import java.io.IOException;

public class StatisticsContinuousSerializer extends ACustomSerializer<StatisticsContinuous> {
   public StatisticsContinuousSerializer() {
      super(StatisticsContinuous.class);
   }

   public void serialize(StatisticsContinuous value, JsonGenerator jgen, SerializerProvider provider) throws IOException, JsonProcessingException {
      jgen.writeStartObject();
      jgen.writeNumberField("count", value.count());
      jgen.writeNumberField("min", value.min());
      jgen.writeNumberField("max", value.max());
      jgen.writeNumberField("mean", value.mean());
      jgen.writeNumberField("confidence", value.meanConfidence());
      jgen.writeNumberField("deviation", value.deviation());
      jgen.writeNumberField("integral", value.integral());
      jgen.writeEndObject();
   }
}
