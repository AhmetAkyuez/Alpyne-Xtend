package com.anylogic.alpyne.sim.data;

import com.anylogic.alpyne.JsonUtils;
import com.anylogic.alpyne.sim.AlpyneReinforcementLearningPlatform;
import com.anylogic.engine.Agent;
import com.anylogic.engine.Engine;
import com.anylogic.engine.Engine.State;
import com.anylogic.rl.data.Action;
import com.anylogic.rl.data.Configuration;
import com.anylogic.rl.data.Observation;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.Date;

public class ModelResponseEngineStatus extends ModelResponse {
   public final State state;
   public final double time;
   public final Date date;
   @JsonProperty("engine_events")
   public final long eventCount;
   @JsonProperty("engine_steps")
   public final long stepCount;
   @JsonProperty("next_engine_event")
   public final double nextEventTime;
   @JsonProperty("next_engine_step")
   public final double nextStepTime;
   public final double progress;
   public final EngineSettings settings;

   public ModelResponseEngineStatus(AlpyneReinforcementLearningPlatform<Agent, Observation, Action, Configuration> platform) {
      super(true, platform.getLastTerminalStatusMessage());
      Engine e = platform.getEngine();
      if (e == null) {
         this.state = null;
         this.time = -1.0;
         this.date = null;
         this.eventCount = -1L;
         this.stepCount = -1L;
         this.nextEventTime = -1.0;
         this.nextStepTime = -1.0;
         this.progress = -1.0;
         this.settings = null;
      } else {
         this.state = e.getState();
         this.time = e.time();
         this.date = e.date();
         this.eventCount = e.getEventCount();
         this.stepCount = e.getStep();
         this.nextEventTime = e.getNextEventTime();
         this.nextStepTime = e.getNextStepTime();
         this.progress = e.getProgress();
         this.settings = platform.getLastEngineSettings();
      }
   }

   @Override
   public String toString() {
      StringBuilder builder = new StringBuilder();
      builder.append("ModelResponse(").append(this.successful ? "SUCCESS" : "FAILURE").append(")");
      if (this.message != null) {
         builder.append(": ").append(this.message);
      }

      builder.append(" -> ").append(JsonUtils.toJson(this));
      return builder.toString();
   }
}
