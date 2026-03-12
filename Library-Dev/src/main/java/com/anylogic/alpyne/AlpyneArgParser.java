package com.anylogic.alpyne;

import java.util.logging.Level;
import org.apache.commons.cli.CommandLine;
import org.apache.commons.cli.CommandLineParser;
import org.apache.commons.cli.DefaultParser;
import org.apache.commons.cli.HelpFormatter;
import org.apache.commons.cli.Options;

public class AlpyneArgParser {
   static final int DEFAULT_PORT = 51150;
   static final Level DEFAULT_LEVEL = Level.INFO;
   static final String DEFAULT_QUERY = "model.jar";
   static final Long DEFAULT_SLEEP = 10L;
   public static final String DEFAULT_DIR = "";
   static final String DEFAULT_LOG_ID = "";
   public final int port;
   public final Level logLevel;
   public final String cpQuery;
   public final long sleep;
   public final String logDir;
   public final String logId;
   public final boolean autoFinish;

   public AlpyneArgParser(String[] args) throws Exception {
      Options options = new Options()
         .addOption("l", "level", true, "Java logging level (default INFO)")
         .addOption("p", "port", true, "Local port to run the server on (default 51150)")
         .addOption("q", "query", true, "Query to match classpath entries against; used to expedite initialization (default model.jar)")
         .addOption("s", "sleep", true, "Milliseconds to sleep in between checks to the engine state when locking (default 10)")
         .addOption("d", "dir", true, "Directory to save model logs in (default current directory)")
         .addOption("f", "autofinish", false, "Whether the 'stop' condition is met, the model will automatically be put in the FINISHED state (default false)")
         .addOption(
            "i",
            "id",
            true,
            "Identifier to put between log name (e.g., alpyne) and extension (.log); use $p for port number, $n for unique number (starts from 1) (default <empty string>)"
         );
      CommandLineParser parser = new DefaultParser();

      try {
         CommandLine line = parser.parse(options, args);
         this.port = Integer.parseInt(line.getOptionValue("p", String.valueOf(51150)));
         Level parsedLevel = DEFAULT_LEVEL;
         if (line.hasOption("l")) {
            String levelString = line.getOptionValue("l");

            try {
               parsedLevel = Level.parse(levelString.toUpperCase());
            } catch (IllegalArgumentException var8) {
               System.out.println("WARNING: Invalid log level '" + levelString + "'. Defaulting to " + DEFAULT_LEVEL.getName());
            }
         }

         this.logLevel = parsedLevel;
         this.cpQuery = line.getOptionValue("q", "model.jar");
         this.sleep = Long.parseLong(line.getOptionValue("s", String.valueOf(DEFAULT_SLEEP)));
         this.logDir = line.getOptionValue("d", "");
         this.autoFinish = line.hasOption("f");
         this.logId = line.getOptionValue("i", "");
      } catch (Exception var91) {
         new HelpFormatter().printHelp("Usage: [OPTIONS]", options);
         throw var91;
      }
   }
}
