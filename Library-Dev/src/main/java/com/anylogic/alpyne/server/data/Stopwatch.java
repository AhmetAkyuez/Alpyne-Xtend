package com.anylogic.alpyne.server.data;

import java.util.HashMap;
import java.util.Map;

public class Stopwatch {
   private static Map<String, Long> startTimes = new HashMap<>();
   private static Map<String, Long> totalTimes = new HashMap<>();
   private static Map<String, Integer> recordCounts = new HashMap<>();

   public static void start(String id) {
      startTimes.put(id, System.currentTimeMillis());
   }

   public static long finish(String id) {
      long dur = System.currentTimeMillis() - startTimes.get(id);
      totalTimes.put(id, totalTimes.getOrDefault(id, 0L) + dur);
      recordCounts.put(id, recordCounts.getOrDefault(id, 0) + 1);
      return dur;
   }
}
