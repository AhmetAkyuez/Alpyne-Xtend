package com.anylogic.alpyne.json;

import com.anylogic.alpyne.sim.ModelManager;
import com.anylogic.alpyne.sim.data.ModelRequestStep;
import com.anylogic.rl.data.Action;
import com.fasterxml.jackson.core.JacksonException;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JavaType;
import com.fasterxml.jackson.databind.JsonNode;
import java.io.IOException;

public class ModelRequestStepDeserializer extends ACustomDeserializer<ModelRequestStep> {
   private static JavaType aType = null;

   public ModelRequestStepDeserializer() {
      super(ModelRequestStep.class);
   }

   public ModelRequestStep<?> deserialize(JsonParser jsonParser, DeserializationContext deserializationContext) throws IOException, JacksonException {
      JsonNode node = (JsonNode)jsonParser.getCodec().readTree(jsonParser);
      Action action = (Action)deserializationContext.readTreeAsValue(node.get("action"), ModelManager.getModelManager().getDescriptor().getActionType());
      return new ModelRequestStep<>(action);
   }
}
