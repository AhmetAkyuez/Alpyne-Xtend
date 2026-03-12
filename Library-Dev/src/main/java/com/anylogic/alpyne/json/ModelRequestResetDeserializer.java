package com.anylogic.alpyne.json;

import com.anylogic.alpyne.sim.ModelManager;
import com.anylogic.alpyne.sim.data.EngineSettings;
import com.anylogic.alpyne.sim.data.ModelIODescriptor;
import com.anylogic.alpyne.sim.data.ModelRequestReset;
import com.anylogic.rl.data.Configuration;
import com.fasterxml.jackson.core.JacksonException;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JavaType;
import com.fasterxml.jackson.databind.JsonNode;
import java.io.IOException;

public class ModelRequestResetDeserializer extends ACustomDeserializer<ModelRequestReset> {
   private static JavaType cType = null;

   public ModelRequestResetDeserializer() {
      super(ModelRequestReset.class);
   }

   public ModelRequestReset<?> deserialize(JsonParser jsonParser, DeserializationContext deserializationContext) throws IOException, JacksonException {
      ModelIODescriptor descriptor = ModelManager.getModelManager().getDescriptor();
      JsonNode node = (JsonNode)jsonParser.getCodec().readTree(jsonParser);
      Configuration config = (Configuration)deserializationContext.readTreeAsValue(node.get("configuration"), descriptor.getConfigurationType());
      EngineSettings settings = (EngineSettings)deserializationContext.readTreeAsValue(node.get("engine_settings"), EngineSettings.class);
      return new ModelRequestReset<>(config, settings);
   }
}
