package com.anylogic.alpyne.sim.data;

public class ModelResponseNoBody extends ModelResponse {
   public final ResponseReason reason;

   public ModelResponseNoBody(ResponseReason reason) {
      this(reason, null);
   }

   public ModelResponseNoBody(ResponseReason reason, String message) {
      super(reason.equals(ResponseReason.SUCCESS), message);
      this.reason = reason;
   }

   @Override
   public String toString() {
      StringBuilder builder = new StringBuilder();
      builder.append("ModelResponse(").append(this.successful ? "SUCCESS" : "FAILURE:" + this.reason.toString()).append(")");
      if (this.message != null) {
         builder.append(": ").append(this.message);
      }

      return builder.toString();
   }
}
