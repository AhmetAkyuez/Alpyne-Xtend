package com.anylogic.alpyne.sim.data;

import com.anylogic.alpyne.json.ModelRequestStepDeserializer;
import com.anylogic.rl.data.Action;
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;

@JsonDeserialize(
   using = ModelRequestStepDeserializer.class
)
public class ModelRequestStep<A extends Action> extends ModelRequest {
   public final A action;

   @JsonCreator
   public ModelRequestStep(@JsonProperty("action") A action) {
      super(RequestType.STEP);
      this.action = action;
   }
}
