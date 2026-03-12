package com.anylogic.alpyne.sim.api;

import com.anylogic.engine.ExperimentReinforcementLearning;
import java.io.File;
import java.io.InputStream;
import java.nio.file.Path;
import java.util.Objects;
import java.util.Properties;
import java.util.zip.ZipFile;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class JarReader {
   private static final Logger log = LoggerFactory.getLogger(JarReader.class);

   public static Class<?> findRLExperiment(String cpQuery) {
      String classpath = System.getProperty("java.class.path");
      String[] classPathValues = classpath.split(File.pathSeparator);

      for (String classPath : classPathValues) {
         if (classPath.contains(cpQuery)) {
            try {
               String expPath = findRLExperimentClassPath(Path.of(classPath));
               Class<?> expClass = Class.forName(expPath);
               if (ExperimentReinforcementLearning.class.isAssignableFrom(expClass)) {
                  log.info(String.format("In jar [%s], class [%s]", classPath, expPath));
                  return expClass;
               }

               log.error(
                  "{} (classloader {}) is not an ExperimentReinforcementLearning (classloader {}) -- SKIPPING",
                  new Object[]{
                     expClass,
                     formatClassLoaderChain(expClass.getClassLoader()),
                     formatClassLoaderChain(ExperimentReinforcementLearning.class.getClassLoader())
                  }
               );
            } catch (ClassNotFoundException var9) {
               log.warn("Skipping {} as RL Experiment candidate due to (handled) error", classPath, var9);
            }
         }
      }

      throw new RuntimeException(String.format("RL Experiment class not found in classpath: %s", cpQuery));
   }

   private static String formatClassLoaderChain(ClassLoader classLoader) {
      StringBuilder sb = new StringBuilder();
      sb.append(classLoader);

      while (classLoader.getParent() != null) {
         classLoader = classLoader.getParent();
         sb.append("->").append(classLoader);
      }

      return sb.toString();
   }

   private static String findRLExperimentClassPath(Path modelJar) {
      try {
         String var11x;
         try (ZipFile zip = new ZipFile(modelJar.toFile())) {
            Properties p = new Properties();

            try (InputStream is = zip.getInputStream(zip.getEntry("com/anylogic/engine/model.properties"))) {
               p.load(is);
            }

            var11x = Objects.requireNonNull(p.getProperty("standaloneExperiment"), "No 'standaloneExperiment' property defined");
         }

         return var11x;
      } catch (Exception var111) {
         throw new RuntimeException(String.format("RL experiment not found in: %s", modelJar), var111);
      }
   }
}
