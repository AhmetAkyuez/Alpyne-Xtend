package com.anylogic.alpyne.json;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.SerializerProvider;
import com.fasterxml.jackson.databind.ser.std.StdSerializer;
import java.io.IOException;

public abstract class ACustomSerializer<T> extends StdSerializer<T> {
   public ACustomSerializer() {
      this(null);
   }

   public ACustomSerializer(Class<T> t) {
      super(t);
   }

   public abstract void serialize(T var1, JsonGenerator var2, SerializerProvider var3) throws IOException, JsonProcessingException;
}
