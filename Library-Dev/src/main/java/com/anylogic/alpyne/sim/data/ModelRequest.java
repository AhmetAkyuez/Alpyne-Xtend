package com.anylogic.alpyne.sim.data;

import com.anylogic.alpyne.JsonUtils;

public abstract class ModelRequest {
   public final RequestType type;

   protected ModelRequest(RequestType type) {
      this.type = type;
   }

   @Override
   public String toString() {
      return JsonUtils.toJson(this);
   }
}
