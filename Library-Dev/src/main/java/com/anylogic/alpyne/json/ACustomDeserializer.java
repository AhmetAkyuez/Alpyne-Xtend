package com.anylogic.alpyne.json;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.deser.std.StdDeserializer;
import java.io.IOException;

public abstract class ACustomDeserializer<T> extends StdDeserializer<T> {
   public ACustomDeserializer(Class<T> t) {
      super(t);
   }

   public abstract T deserialize(JsonParser var1, DeserializationContext var2) throws IOException;
}
