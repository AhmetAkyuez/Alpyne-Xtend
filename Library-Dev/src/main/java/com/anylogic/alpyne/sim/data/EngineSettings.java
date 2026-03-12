package com.anylogic.alpyne.sim.data;

import com.anylogic.alpyne.json.EngineSettingsDeserializer;
import com.anylogic.engine.Engine;
import com.anylogic.engine.Pair;
import com.anylogic.engine.TimeUnits;
import com.anylogic.engine.Utilities;
import com.fasterxml.jackson.annotation.JsonAutoDetect;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonAutoDetect.Visibility;
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Date;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Random;
import lombok.NonNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@JsonAutoDetect(
   fieldVisibility = Visibility.ANY
)
@JsonDeserialize(
   using = EngineSettingsDeserializer.class
)
public class EngineSettings {
   private static final Logger log = LoggerFactory.getLogger(EngineSettings.class);
   private TimeUnits units;
   @JsonProperty("start_time")
   private Double startTime;
   @JsonProperty("start_date")
   private Date startDate;
   @JsonProperty("stop_time")
   private Double stopTime;
   @JsonProperty("stop_date")
   private Date stopDate;
   private Long seed;

   public static EngineSettings fillFrom(@NonNull Engine engine) {
      if (engine == null) {
         throw new NullPointerException("engine is marked non-null but is null");
      } else {
         return new EngineSettings(engine.getTimeUnit(), engine.getStartTime(), engine.getStartDate(), engine.getStopTime(), engine.getStopDate(), null);
      }
   }

   public static EngineSettings copyOf(@NonNull EngineSettings other) {
      if (other == null) {
         throw new NullPointerException("other is marked non-null but is null");
      } else {
         return new EngineSettings(other.units, other.startTime, other.startDate, other.stopTime, other.stopDate, other.seed);
      }
   }

   public EngineSettings(@NonNull TimeUnits units, @NonNull Double startTime, @NonNull Date startDate, Double stopTime, Date stopDate, Long seed) {
      if (units == null) {
         throw new NullPointerException("units is marked non-null but is null");
      } else if (startDate == null) {
         throw new NullPointerException("startDate is marked non-null but is null");
      } else if (startTime == null) {
         throw new NullPointerException("startTime is marked non-null but is null");
      } else if (startDate == null) {
         throw new NullPointerException("startDate is marked non-null but is null");
      } else if (units == null) {
         throw new NullPointerException("units is marked non-null but is null");
      } else if (startTime == null) {
         throw new NullPointerException("startTime is marked non-null but is null");
      } else if (startDate == null) {
         throw new NullPointerException("startDate is marked non-null but is null");
      } else {
         log.debug("Constructing\tw/start = {} | {}, finish = {} | {}, seed = {}", new Object[]{startTime, startDate, stopTime, stopDate, seed});
         this.units = units;
         this.startTime = startTime;
         this.startDate = startDate;
         this.stopTime = stopTime;
         this.stopDate = stopDate;
         this.seed = seed;
         this.resolve();
         log.debug("Constructed\tw/start = {} | {}, finish = {} | {}", new Object[]{startTime, startDate, stopTime, stopDate});
      }
   }

   public EngineSettings(@NonNull TimeUnits units, @NonNull Double startTime, @NonNull Date startDate, Double stopTime, Long seed) {
      this(
         units,
         startTime,
         startDate,
         stopTime,
         stopTime != null && !stopTime.isInfinite() ? Utilities.addToDate(startDate, units, stopTime - startTime) : null,
         seed
      );
      if (units == null) {
         throw new NullPointerException("units is marked non-null but is null");
      } else if (startDate == null) {
         throw new NullPointerException("startDate is marked non-null but is null");
      } else if (startTime == null) {
         throw new NullPointerException("startTime is marked non-null but is null");
      } else if (startDate == null) {
         throw new NullPointerException("startDate is marked non-null but is null");
      } else if (units == null) {
         throw new NullPointerException("units is marked non-null but is null");
      } else if (startTime == null) {
         throw new NullPointerException("startTime is marked non-null but is null");
      } else if (startDate == null) {
         throw new NullPointerException("startDate is marked non-null but is null");
      }
   }

   public EngineSettings(@NonNull TimeUnits units, @NonNull Double startTime, @NonNull Date startDate, Date stopDate, Long seed) {
      this(units, startTime, startDate, stopDate == null ? null : Utilities.differenceInCalendarUnits(units, startDate, stopDate), seed);
      if (units == null) {
         throw new NullPointerException("units is marked non-null but is null");
      } else if (startDate == null) {
         throw new NullPointerException("startDate is marked non-null but is null");
      } else if (startTime == null) {
         throw new NullPointerException("startTime is marked non-null but is null");
      } else if (startDate == null) {
         throw new NullPointerException("startDate is marked non-null but is null");
      } else if (units == null) {
         throw new NullPointerException("units is marked non-null but is null");
      } else if (startTime == null) {
         throw new NullPointerException("startTime is marked non-null but is null");
      } else if (startDate == null) {
         throw new NullPointerException("startDate is marked non-null but is null");
      }
   }

   public void applyTo(@NonNull Engine engine) {
      if (engine == null) {
         throw new NullPointerException("engine is marked non-null but is null");
      } else {
         if (this.units != null) {
            engine.setTimeUnit(this.units);
         }

         if (this.startTime != null) {
            engine.setStartTime(this.startTime);
         }

         if (this.startDate != null) {
            engine.setStartDate(this.startDate);
         }

         if (this.stopTime != null && this.stopDate != null) {
            Date timeBasedStopDate = Utilities.addToDate(engine.getStartDate(), engine.getTimeUnit(), this.stopTime);
            engine.setStopDate(timeBasedStopDate.after(this.stopDate) ? timeBasedStopDate : this.stopDate);
         } else if (this.stopTime != null) {
            engine.setStopTime(this.stopTime);
         } else if (this.stopDate != null) {
            engine.setStopDate(this.stopDate);
         }

         if (this.seed != null) {
            engine.setDefaultRandomGenerator(new Random(this.seed));
         }
      }
   }

   @Override
   public String toString() {
      return String.format(
         "EngineSettings(start=%s %s|%s, end=%s %s|%s, seed=%s)",
         this.startTime,
         this.units,
         this.startDate,
         this.stopTime,
         this.units,
         this.stopDate,
         this.seed
      );
   }

   private void resolve() {
      if (this.units == null) {
         this.units = TimeUnits.SECOND;
      }

      Date now = new Date();
      if (Objects.isNull(this.startTime) && Objects.isNull(this.startDate) && Objects.isNull(this.stopTime) && Objects.isNull(this.stopDate)) {
         this.startTime = 0.0;
         this.stopTime = Double.POSITIVE_INFINITY;
         this.startDate = now;
         this.stopDate = null;
      } else {
         if (this.startTime != null && this.stopTime != null && this.stopTime < this.startTime) {
            Double temp = this.startTime;
            this.startTime = this.stopTime;
            this.stopTime = temp;
         }

         if (this.startDate != null && this.stopDate != null && this.stopDate.before(this.startDate)) {
            Date tempDate = this.startDate;
            this.startDate = this.stopDate;
            this.stopDate = tempDate;
         }

         if (this.startTime < 0.0) {
            this.stopTime = this.stopTime + Math.abs(this.startTime);
            this.startTime = this.startTime + Math.abs(this.startTime);
         }

         if (this.startDate != null && this.stopDate != null && Objects.isNull(this.startTime)) {
            if (this.stopTime != null) {
               this.startTime = this.stopTime - Utilities.differenceInCalendarUnits(this.units, this.startDate, this.stopDate);
            } else {
               this.startTime = 0.0;
               this.stopTime = Utilities.differenceInCalendarUnits(this.units, this.startDate, this.stopDate);
            }
         } else if (this.startTime != null && this.stopTime != null && Objects.isNull(this.startDate)) {
            if (this.stopDate != null) {
               this.startDate = Utilities.addToDate(this.stopDate, this.units, this.startTime - this.stopTime);
            } else {
               this.startDate = now;
               this.stopDate = Utilities.addToDate(now, this.units, this.stopTime - this.startTime);
            }
         }

         if (this.startDate != null && Objects.isNull(this.stopTime)) {
            if (this.stopDate != null) {
               this.stopTime = this.startTime + Utilities.differenceInCalendarUnits(this.units, this.startDate, this.stopDate);
            } else {
               this.stopTime = Double.POSITIVE_INFINITY;
            }
         } else if (this.startTime != null && Objects.isNull(this.stopDate)) {
            this.stopDate = this.stopTime != null && Utilities.isFinite(this.stopTime)
               ? Utilities.addToDate(this.startDate, this.units, this.stopTime - this.startTime)
               : null;
         }

         if (Objects.isNull(this.startDate) && this.stopTime != null && this.stopDate != null) {
            this.startDate = Utilities.addToDate(this.stopDate, this.units, -this.stopTime);
            this.startTime = 0.0;
         } else if (Objects.isNull(this.stopDate) && this.startTime != null) {
            this.stopTime = Double.POSITIVE_INFINITY;
         }

         if (Objects.isNull(this.startTime)) {
            this.startTime = 0.0;
            if (Objects.isNull(this.stopTime)) {
               this.startDate = now;
               this.stopTime = Utilities.differenceInCalendarUnits(this.units, this.startDate, this.stopDate);
            }
         }

         if (Objects.isNull(this.startDate) && Objects.isNull(this.stopDate)) {
            this.startDate = now;
            this.stopDate = Utilities.isFinite(this.stopTime) ? Utilities.addToDate(now, this.units, this.stopTime - this.startTime) : null;
         }

         if (this.stopTime < 0.0) {
            this.stopTime = Math.abs(this.stopTime);
         }

         if (this.startDate != null && this.stopDate != null && this.stopDate.before(this.startDate)) {
            Date tempDate = this.startDate;
            this.startDate = this.stopDate;
            this.stopDate = tempDate;
         }

         if (this.startTime != null && this.startDate != null && this.stopTime != Double.POSITIVE_INFINITY && this.stopDate != null) {
            Date timeBasedStopDate = Utilities.addToDate(this.startDate, this.units, this.stopTime - this.startTime);
            if (timeBasedStopDate.after(this.stopDate)) {
               this.stopDate = timeBasedStopDate;
            } else if (timeBasedStopDate.before(this.stopDate)) {
               this.stopTime = Utilities.differenceInCalendarUnits(this.units, this.startDate, this.stopDate);
            }
         }

         log.trace(
            "Resolution final: units={}, start=({} | {}), finish=({} | {})",
            new Object[]{this.units, this.startTime, this.startDate, this.stopTime, this.stopDate}
         );
      }
   }

   public Map<String, Pair<Object, Object>> differencesTo(@NonNull EngineSettings other) {
      if (other == null) {
         throw new NullPointerException("other is marked non-null but is null");
      } else {
         HashMap<String, Pair<Object, Object>> differences = new HashMap<>();
         if (!this.units.equals(other.units)) {
            differences.put("units", new Pair(this.units, other.units));
         }

         if (!Objects.equals(this.startTime, other.startTime)) {
            differences.put("startTime", new Pair(this.startTime, other.startTime));
         }

         if (!Objects.equals(this.startDate, other.startDate)) {
            differences.put("startDate", new Pair(this.startDate, other.startDate));
         }

         if (!Objects.equals(this.stopTime, other.stopTime)) {
            differences.put("stopTime", new Pair(this.stopTime, other.stopTime));
         }

         if (!Objects.equals(this.stopDate, other.stopDate)) {
            differences.put("stopDate", new Pair(this.stopDate, other.stopDate));
         }

         return differences;
      }
   }

   public TimeUnits getUnits() {
      return this.units;
   }

   public Double getStartTime() {
      return this.startTime;
   }

   public Date getStartDate() {
      return this.startDate;
   }

   public Double getStopTime() {
      return this.stopTime;
   }

   public Date getStopDate() {
      return this.stopDate;
   }

   public Long getSeed() {
      return this.seed;
   }

   @Retention(RetentionPolicy.RUNTIME)
   @Target({ElementType.FIELD, ElementType.PARAMETER})
   public @interface ValidOneOfTypes {
      Class<?>[] value();
   }
}
