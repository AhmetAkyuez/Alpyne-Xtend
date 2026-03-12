package com.anylogic.alpyne.sim.data;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

public class ModelRequestOutput extends ModelRequest {
   public final String[] names;

   @JsonCreator
   public ModelRequestOutput(@JsonProperty("names") String[] names) {
      super(RequestType.OUTPUT);
      this.names = names;
   }
}
