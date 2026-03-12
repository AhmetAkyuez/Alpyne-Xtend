package com.anylogic.alpyne.json;

import com.anylogic.engine.analysis.StatisticsDiscrete;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.SerializerProvider;
import java.io.IOException;

public class StatisticsDiscreteSerializer extends ACustomSerializer<StatisticsDiscrete> {
   public StatisticsDiscreteSerializer() {
      super(StatisticsDiscrete.class);
   }

   public void serialize(StatisticsDiscrete value, JsonGenerator jgen, SerializerProvider provider) throws IOException, JsonProcessingException {
      jgen.writeStartObject();
      jgen.writeNumberField("count", value.count());
      jgen.writeNumberField("min", value.min());
      jgen.writeNumberField("max", value.max());
      jgen.writeNumberField("mean", value.mean());
      jgen.writeNumberField("confidence", value.meanConfidence());
      jgen.writeNumberField("deviation", value.deviation());
      jgen.writeNumberField("sum", value.sum());
      jgen.writeEndObject();
   }
}
