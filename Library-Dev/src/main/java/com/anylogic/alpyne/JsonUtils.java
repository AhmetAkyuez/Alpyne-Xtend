package com.anylogic.alpyne;

import com.anylogic.alpyne.json.ACustomDeserializer;
import com.anylogic.alpyne.json.ACustomSerializer;
import com.anylogic.alpyne.json.DataSetSerializer;
import com.anylogic.alpyne.json.Histogram1DSerializer;
import com.anylogic.alpyne.json.Histogram2DSerializer;
import com.anylogic.alpyne.json.ModelRequestResetDeserializer;
import com.anylogic.alpyne.json.ModelRequestStepDeserializer;
import com.anylogic.alpyne.json.StatisticsContinuousSerializer;
import com.anylogic.alpyne.json.StatisticsDiscreteSerializer;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.JsonParser.Feature;
import com.fasterxml.jackson.core.json.JsonReadFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.module.SimpleModule;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class JsonUtils {
   private static final Logger log = LoggerFactory.getLogger(JsonUtils.class);
   public static final ObjectMapper mapper = new ObjectMapper();

   private static void registerSers(Class<?>... serClasses) {
      SimpleModule module = new SimpleModule();

      for (Class<?> c : serClasses) {
         try {
            ACustomSerializer s = (ACustomSerializer)c.getDeclaredConstructor().newInstance();
            module.addSerializer(s.handledType(), s);
         } catch (Exception var7) {
            var7.printStackTrace();
         }
      }

      mapper.registerModule(module);
   }

   private static void registerDesers(Class<?>... deserClasses) {
      SimpleModule module = new SimpleModule();

      for (Class<?> c : deserClasses) {
         try {
            ACustomDeserializer s = (ACustomDeserializer)c.getDeclaredConstructor().newInstance();
            module.addDeserializer(s.handledType(), s);
         } catch (Exception var7) {
            var7.printStackTrace();
         }
      }

      mapper.registerModule(module);
   }

   public static String toJson(Object obj) {
      String output = null;

      try {
         output = mapper.writeValueAsString(obj);
      } catch (JsonProcessingException var3) {
         log.error(String.format("Failed to convert object '%s' to JSON; returning null.", obj), var3);
      }

      return output;
   }

   public static <T> T fromJson(String json, Class<T> type) throws JsonProcessingException {
      return (T)mapper.readValue(json, type);
   }

   public static <T> T fromJson(String json, Class<T> type, T defaultValue) {
      T output;
      try {
         output = fromJson(json, type);
      } catch (JsonProcessingException var5) {
         if (defaultValue != null) {
            output = defaultValue;
         } else {
            log.error(String.format("Failed to convert string '%s' to type '%s' and no default provided; returning null.", json, type), var5);
            output = null;
         }
      }

      return output;
   }

   static {
      mapper.configure(SerializationFeature.FAIL_ON_EMPTY_BEANS, false);
      mapper.enable(new Feature[]{JsonReadFeature.ALLOW_NON_NUMERIC_NUMBERS.mappedFeature()});
      registerSers(
         DataSetSerializer.class,
         Histogram1DSerializer.class,
         Histogram2DSerializer.class,
         StatisticsContinuousSerializer.class,
         StatisticsDiscreteSerializer.class
      );
      registerDesers(ModelRequestResetDeserializer.class, ModelRequestStepDeserializer.class);
      mapper.findAndRegisterModules().configure(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS, false);
   }
}
