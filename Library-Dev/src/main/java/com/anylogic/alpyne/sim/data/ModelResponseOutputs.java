package com.anylogic.alpyne.sim.data;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.Arrays;

public class ModelResponseOutputs extends ModelResponse {
   @JsonProperty("model_datas")
   public final ModelData[] modelDatas;

   public ModelResponseOutputs(ModelData[] modelDatas) {
      super(true);
      this.modelDatas = modelDatas;
   }

   @Override
   public String toString() {
      StringBuilder builder = new StringBuilder();
      builder.append("ModelResponse(").append(this.successful ? "SUCCESS" : "FAILURE").append(")");
      if (this.message != null) {
         builder.append(": ").append(this.message);
      }

      if (this.modelDatas != null) {
         builder.append(" -> ").append(Arrays.toString((Object[])this.modelDatas));
      }

      return builder.toString();
   }
}
