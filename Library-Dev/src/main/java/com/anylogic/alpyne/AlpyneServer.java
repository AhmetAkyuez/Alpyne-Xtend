package com.anylogic.alpyne;

import com.anylogic.alpyne.server.api.ModelManagerBinder;
import com.anylogic.alpyne.sim.ModelManager;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.PrintStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Map;
import java.util.logging.FileHandler;
import java.util.logging.LogManager;
import org.glassfish.grizzly.http.server.HttpServer;
import org.glassfish.jersey.grizzly2.httpserver.GrizzlyHttpServerFactory;
import org.glassfish.jersey.jackson.internal.jackson.jaxrs.json.JacksonJaxbJsonProvider;
import org.glassfish.jersey.server.ResourceConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class AlpyneServer {
   private static final Logger log = LoggerFactory.getLogger(AlpyneServer.class);
   public static final String BASE_URI = "http://localhost";

   public static HttpServer createServer(int port, ModelManager manager) throws IOException {
      long startMS = System.currentTimeMillis();
      JacksonJaxbJsonProvider provider = new JacksonJaxbJsonProvider();
      provider.setMapper(JsonUtils.mapper);
      ResourceConfig rc = new ResourceConfig()
         .register(new ModelManagerBinder(manager))
         .addProperties(Map.of("jersey.config.disableAutoDiscovery", true, "jersey.config.server.wadl.disableWadl", true))
         .register(provider)
         .packages(new String[]{"com.anylogic.alpyne.server.api"});
      String uri = String.format("%s:%s/", "http://localhost", port);
      HttpServer server = GrizzlyHttpServerFactory.createHttpServer(URI.create(uri), rc);
      Runtime.getRuntime().addShutdownHook(new Thread(() -> {
         log.info("Stopping server...");
         server.shutdownNow();
      }, "shutdownHook"));
      log.debug("Server created in {} ms", System.currentTimeMillis() - startMS);
      return server;
   }

   public static void main(String[] args) throws Exception {
      AlpyneArgParser argp = new AlpyneArgParser(args);

      try {
         Path logBasePath = Paths.get(argp.logDir.isEmpty() ? "." : argp.logDir);
         if (!logBasePath.endsWith("Logs")) {
            logBasePath = logBasePath.resolve("Logs");
         }

         Files.createDirectories(logBasePath);
         String modelLogNameTemplate = String.format("model%s.log", argp.logId).replace("$p", String.valueOf(argp.port));
         String alpyneLogNameTemplate = String.format("alpyne%s.log", argp.logId).replace("$p", String.valueOf(argp.port));
         String rawScanLogName = "raw_scan_results.log";
         Path modelLogPath = logBasePath.resolve(modelLogNameTemplate);
         Path alpyneLogPath = logBasePath.resolve(alpyneLogNameTemplate);
         Path rawScanLogPath = logBasePath.resolve(rawScanLogName);

         if (modelLogPath.toString().contains("$n")) {
            int i = 1;

            while (Files.exists(Paths.get(modelLogPath.toString().replace("$n", String.valueOf(i))))) {
               i++;
            }

            modelLogPath = Paths.get(modelLogPath.toString().replace("$n", String.valueOf(i)));
         }

         if (alpyneLogPath.toString().contains("$n")) {
            int i = 1;

            while (Files.exists(Paths.get(alpyneLogPath.toString().replace("$n", String.valueOf(i))))) {
               i++;
            }

            alpyneLogPath = Paths.get(alpyneLogPath.toString().replace("$n", String.valueOf(i)));
         }

         PrintStream outStream = new PrintStream(new FileOutputStream(modelLogPath.toFile()), true, StandardCharsets.UTF_8);
         System.setOut(outStream);
         System.setErr(outStream);

         try (InputStream is = AlpyneServer.class.getClassLoader().getResourceAsStream("logging.properties")) {
            if (is != null) {
               LogManager.getLogManager().readConfiguration(is);
            } else {
               System.out.println("WARNING: 'logging.properties' not found in JAR. Using default logging settings.");
            }
         }

         FileHandler fileHandler = new FileHandler(alpyneLogPath.toString(), 0, 1, false);
         fileHandler.setFormatter(new LogFormatter());
         java.util.logging.Logger.getLogger("").addHandler(fileHandler);
         java.util.logging.Logger.getLogger("com.anylogic.alpyne").setLevel(argp.logLevel);
         log.info(String.format("[PID=%s] Initializing...", ProcessHandle.current().pid()));
         ModelManager manager = ModelManager.setup(argp.cpQuery, argp.sleep, argp.autoFinish, rawScanLogPath, null);
         HttpServer server = createServer(argp.port, manager);
         server.start();
         Thread.currentThread().join();
      } catch (Throwable var171) {
         System.err.println("###### ALPYNE FATAL STARTUP ERROR ######");
         var171.printStackTrace(System.err);
         System.err.println("########################################");
         System.exit(1);
      }

      log.info("Alpyne terminated.");
   }
}

