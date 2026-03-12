package com.anylogic.alpyne.server.data;

import com.anylogic.engine.Pair;
import jakarta.ws.rs.HttpMethod;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.QueryParam;
import java.lang.annotation.Annotation;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;
import org.glassfish.jersey.server.internal.scanning.PackageNamesScanner;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class EndpointScanner {
   private static final Logger log = LoggerFactory.getLogger(EndpointScanner.class);

   public static List<EndpointScanner.EndpointEntry> getEntries(Class<?> cls) {
      List<EndpointScanner.EndpointEntry> entries = new ArrayList<>();
      if (!cls.isAnnotationPresent(Path.class)) {
         return entries;
      } else {
         String root = ((Path)cls.getAnnotation(Path.class)).value();
         if (!root.startsWith("/")) {
            root = "/" + root;
         }

         for (Method meth : cls.getDeclaredMethods()) {
            String operation = meth.getName();
            if (!operation.contains("$")) {
               String path = meth.isAnnotationPresent(Path.class) ? ((Path)meth.getAnnotation(Path.class)).value() : "";
               String endpoint = (root + path).replaceAll("/+", "/");
               Optional<Annotation> methAnno = Arrays.stream(meth.getAnnotations())
                  .filter(ann -> ann.annotationType().isAnnotationPresent(HttpMethod.class))
                  .findFirst();
               String method = "???";
               if (methAnno.isPresent()) {
                  method = ((HttpMethod)methAnno.get().annotationType().getAnnotation(HttpMethod.class)).value();
               }

               // The Fix: Explicitly cast the collector to ensure the compiler correctly infers the generic types.
               List<Pair<String, String>> arguments = Arrays.stream(meth.getParameters()).map(param -> {
                  String p_type = param.getType().getSimpleName();
                  String p_name = param.isAnnotationPresent(QueryParam.class) ? ((QueryParam)param.getAnnotation(QueryParam.class)).value() : param.getName();
                  return new Pair<String, String>(p_type, p_name);
               }).collect(Collectors.toList()); // Line 49 in the original file block

               String outputs = meth.isAnnotationPresent(Produces.class) ? ((Produces)meth.getAnnotation(Produces.class)).value()[0] : "NONE";
               entries.add(new EndpointScanner.EndpointEntry(operation, method, endpoint, arguments, outputs));
            }
         }

         return entries;
      }
   }

   public static List<EndpointScanner.EndpointEntry> getEntries(String pkg) {
      List<EndpointScanner.EndpointEntry> entries = new ArrayList<>();
      PackageNamesScanner scan = new PackageNamesScanner(new String[]{pkg}, true);

      try {
         while (scan.hasNext()) {
            String clsName = scan.next();
            String fullClsName = clsName.replace(".class", "");
            if (fullClsName.contains("/")) {
               fullClsName = fullClsName.replaceAll("/", ".");
            } else {
               fullClsName = pkg + fullClsName;
            }

            try {
               Class<?> cls = Class.forName(fullClsName);
               entries.addAll(getEntries(cls));
            } catch (ClassNotFoundException var7) {
               log.warn(String.format("Skipping %s (%s)", fullClsName, clsName), var7);
            }
         }
      } catch (Throwable var8) {
         try {
            scan.close();
         } catch (Throwable var6) {
            var8.addSuppressed(var6);
         }

         throw var8;
      }

      scan.close();
      return entries;
   }

   public static class EndpointEntry {
      String operationDescription;
      String httpMethod;
      String urlEndpoint;
      List<Pair<String, String>> arguments;
      String responseType;

      public EndpointEntry(String operationDescription, String httpMethod, String urlEndpoint, List<Pair<String, String>> arguments, String responseType) {
         this.operationDescription = operationDescription;
         this.httpMethod = httpMethod;
         this.urlEndpoint = urlEndpoint;
         this.arguments = arguments;
         this.responseType = responseType;
      }

      @Override
      public String toString() {
         return String.format(
            "%7s %s (%s) -> %s : %s",
            this.httpMethod,
            this.urlEndpoint,
            this.arguments.stream().map(p -> String.format("%s %s", p.getFirst(), p.getSecond())).collect(Collectors.joining(", ")),
            this.responseType,
            this.operationDescription
         );
      }

      public String getOperationDescription() {
         return this.operationDescription;
      }

      public String getHttpMethod() {
         return this.httpMethod;
      }

      public String getUrlEndpoint() {
         return this.urlEndpoint;
      }

      public List<Pair<String, String>> getArguments() {
         return this.arguments;
      }

      public String getResponseType() {
         return this.responseType;
      }
   }
}
