package com.anylogic.alpyne.sim.data;

import com.fasterxml.jackson.annotation.JsonCreator;

public class ModelRequestEngineStatus extends ModelRequest {
   @JsonCreator
   public ModelRequestEngineStatus() {
      super(RequestType.ENGINE_STATUS);
   }
}
