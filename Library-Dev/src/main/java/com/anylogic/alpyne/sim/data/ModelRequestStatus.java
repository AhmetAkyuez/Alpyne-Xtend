package com.anylogic.alpyne.sim.data;

import com.fasterxml.jackson.annotation.JsonCreator;

public class ModelRequestStatus extends ModelRequest {
   @JsonCreator
   public ModelRequestStatus() {
      super(RequestType.STATUS);
   }
}
