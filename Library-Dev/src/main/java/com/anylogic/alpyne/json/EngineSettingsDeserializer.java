package com.anylogic.alpyne.json;

import com.anylogic.alpyne.sim.ModelManager;
import com.anylogic.alpyne.sim.data.EngineSettings;
import com.anylogic.engine.TimeUnits;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonNode;
import java.io.IOException;
import java.util.Date;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class EngineSettingsDeserializer extends ACustomDeserializer<EngineSettings> {
   private static final Logger log = LoggerFactory.getLogger(EngineSettingsDeserializer.class);

   public EngineSettingsDeserializer() {
      super(EngineSettings.class);
   }

   public EngineSettings deserialize(JsonParser jsonParser, DeserializationContext deserializationContext) throws IOException {
      EngineSettings template = ModelManager.getModelManager().getDescriptor().getEngineSettingsTemplate();
      JsonNode node = (JsonNode)jsonParser.getCodec().readTree(jsonParser);
      TimeUnits units = node.has("units") && !node.get("units").isNull() ? TimeUnits.valueOf(node.get("units").asText()) : template.getUnits();
      Double startTime = node.has("start_time") && !node.get("start_time").isNull() ? node.get("start_time").asDouble() : template.getStartTime();
      Date startDate = node.has("start_date") && !node.get("start_date").isNull()
         ? deserializationContext.parseDate(node.get("start_date").asText())
         : template.getStartDate();
      Long seed;
      if (node.has("seed")) {
         seed = node.get("seed").isNull() ? null : node.get("seed").asLong();
      } else {
         seed = template.getSeed();
      }

      Date stopDate = node.has("stop_date") && !node.get("stop_date").isNull()
         ? deserializationContext.parseDate(node.get("stop_date").asText())
         : template.getStopDate();
      Double stopTime;
      if (node.has("stop_time")) {
         JsonNode n = node.get("stop_time");
         if (n.isNull()) {
            stopTime = null;
         } else if (n.isTextual()) {
            if (!n.asText().equals("Infinity")) {
               throw new IOException(String.format("Unhandled text value for stop time '%s'", n.asText()));
            }

            stopTime = null;
         } else {
            stopTime = n.asDouble();
         }
      } else {
         stopTime = template.getStopTime();
      }

      EngineSettings settings;
      if (node.has("stop_time") && !node.has("stop_date")) {
         log.debug("Constructing with both starts and stop time");
         settings = new EngineSettings(units, startTime, startDate, stopTime, seed);
      } else if (!node.has("stop_time") && node.has("stop_date")) {
         log.debug("Constructing with both starts and stop date");
         settings = new EngineSettings(units, startTime, startDate, stopDate, seed);
      } else {
         log.debug("Constructing with both starts and stops");
         settings = new EngineSettings(units, startTime, startDate, stopTime, stopDate, seed);
      }

      return settings;
   }
}
