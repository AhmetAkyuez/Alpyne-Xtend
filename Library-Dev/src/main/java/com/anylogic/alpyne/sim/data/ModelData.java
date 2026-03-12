package com.anylogic.alpyne.sim.data;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.NonNull;

public class ModelData {
   public final String name;
   public final String type;
   // This is the single, authoritative field for the parameter's value.
   // Its name 'value' is required for the API communication with Python.
   public final Object value;

   @JsonCreator
   public ModelData(
      @JsonProperty("name") @NonNull String name,
      @JsonProperty("type") String type,
      @JsonProperty("value") Object value
   ) {
      if (name == null) {
         throw new NullPointerException("name is marked non-null but is null");
      }
      this.name = name;
      this.type = type;
      this.value = value;
   }

   public ModelData(@NonNull String name, Object value) {
      this(name, value == null ? "N/A" : value.getClass().getSimpleName(), value);
   }

   public ModelData(@NonNull String name, Class<?> cls, Object value) {
      this(name, cls == null ? "N/A" : cls.getSimpleName(), value);
   }

   @Override
   public String toString() {
      // For logging purposes, we can label the 'value' as 'default'.
      String valueStr = this.value != null ? String.format(", default=%s", this.value) : "";
      return String.format("(%s)%s%s", this.type, this.name, valueStr);
   }

   public Object getValue() {
      return this.value;
   }
}

