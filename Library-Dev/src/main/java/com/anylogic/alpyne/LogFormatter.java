package com.anylogic.alpyne;

import java.io.PrintWriter;
import java.io.StringWriter;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.logging.Formatter;
import java.util.logging.LogRecord;

public class LogFormatter extends Formatter {
   public static final int SPACES_TO_TEXT = 32;
   private static final String SPACES_PREFIX = " ".repeat(30);
   public static final String ANSI_RESET = "\u001b[0m";
   public static final String ANSI_BLACK = "\u001b[30m";
   public static final String ANSI_RED = "\u001b[31m";
   public static final String ANSI_GREEN = "\u001b[32m";
   public static final String ANSI_YELLOW = "\u001b[33m";
   public static final String ANSI_BLUE = "\u001b[34m";
   public static final String ANSI_PURPLE = "\u001b[35m";
   public static final String ANSI_CYAN = "\u001b[36m";
   public static final String ANSI_WHITE = "\u001b[37m";
   public static final String DEFAULT_COLOR = "\u001b[34m";
   private final boolean enableColor;
   private final String clsTextColor;
   private final String logTextColor;

   public LogFormatter() {
      this(false);
   }

   public LogFormatter(boolean enableColor) {
      this(enableColor ? "\u001b[34m" : null);
   }

   public LogFormatter(String logColor) {
      this.enableColor = logColor != null && !logColor.isEmpty();
      this.clsTextColor = logColor;
      this.logTextColor = logColor;
   }

   @Override
   public String format(LogRecord record) {
      StringBuilder builder = new StringBuilder();
      if (this.enableColor) {
         builder.append("\u001b[37m");
      }

      builder.append("[").append(calcDate(record.getMillis())).append("] ");
      String lvlName = record.getLevel().getName();
      String lvlColor = this.levelToColor(lvlName);
      if (this.enableColor) {
         builder.append(lvlColor);
      }

      builder.append(String.format("%-7s ", lvlName));
      builder.append("@ ");
      if (this.enableColor) {
         builder.append(this.clsTextColor);
      }

      String[] components = record.getSourceClassName().split("\\.");
      builder.append(components[components.length - 1]);
      builder.append(".");
      builder.append(record.getSourceMethodName());
      if (this.enableColor) {
         builder.append("\u001b[37m");
      }

      builder.append("\n").append(SPACES_PREFIX);
      if (this.enableColor) {
         builder.append(lvlColor);
      }

      builder.append("| ");
      if (this.enableColor) {
         builder.append(this.logTextColor);
      }

      builder.append(record.getMessage());
      Object[] params = record.getParameters();
      if (params != null) {
         if (this.enableColor) {
            builder.append("\u001b[37m");
         }

         builder.append("\n").append(SPACES_PREFIX);
         if (this.enableColor) {
            builder.append(lvlColor);
         }

         builder.append("| ");

         for (int i = 0; i < params.length; i++) {
            builder.append(params[i]);
            if (i < params.length - 1) {
               builder.append(", ");
            }
         }
      }

      if (this.enableColor) {
         builder.append("\u001b[0m");
      }

      builder.append("\n");
      if (record.getThrown() != null) {
         StringWriter writer = new StringWriter();
         record.getThrown().printStackTrace(new PrintWriter(writer));
         String trace = writer.toString();
         String indent = " ".repeat(SPACES_PREFIX.length() + 2);
         trace = indent + trace.replace("\n", "\n" + indent);
         builder.append(trace);
         builder.append("\n");
      }

      return builder.toString();
   }

   private String levelToColor(String lvlName) {
      String color = "\u001b[0m";

      return switch (lvlName) {
         case "SEVERE", "WARNING" -> "\u001b[31m";
         case "INFO" -> "\u001b[32m";
         default -> "\u001b[33m";
      };
   }

   public static String calcDate(long millisecs) {
      SimpleDateFormat date_format = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS");
      Date resultdate = new Date(millisecs);
      return date_format.format(resultdate);
   }
}
