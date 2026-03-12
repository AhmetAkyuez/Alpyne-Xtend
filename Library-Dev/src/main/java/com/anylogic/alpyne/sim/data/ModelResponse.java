package com.anylogic.alpyne.sim.data;

import com.fasterxml.jackson.annotation.JsonIgnore;
import java.util.Objects;

public abstract class ModelResponse {
   @JsonIgnore
   public final boolean successful;
   public final String message;

   protected ModelResponse(boolean successful) {
      this.successful = successful;
      this.message = null;
   }

   protected ModelResponse(boolean successful, Object message) {
      this.successful = successful;
      this.message = Objects.toString(message, null);
   }

   @Override
   public String toString() {
      StringBuilder builder = new StringBuilder();
      builder.append("ModelResponse(").append(this.successful ? "SUCCESS" : "FAILURE").append(")");
      if (this.message != null) {
         builder.append(": ").append(this.message);
      }

      return builder.toString();
   }
}
