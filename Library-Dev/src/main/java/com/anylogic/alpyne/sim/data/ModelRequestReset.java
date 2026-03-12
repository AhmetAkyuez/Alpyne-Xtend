package com.anylogic.alpyne.sim.data;

import com.anylogic.alpyne.json.ModelRequestResetDeserializer;
import com.anylogic.rl.data.Configuration;
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;

@JsonDeserialize(
   using = ModelRequestResetDeserializer.class
)
public class ModelRequestReset<C extends Configuration> extends ModelRequest {
   public final C configuration;
   @JsonProperty("engine_settings")
   public final EngineSettings engineSettings;

   @JsonCreator
   public ModelRequestReset(@JsonProperty("configuration") C configuration, @JsonProperty("engine_settings") EngineSettings engineSettings) {
      super(RequestType.RESET);
      this.configuration = configuration;
      this.engineSettings = engineSettings;
   }
}
