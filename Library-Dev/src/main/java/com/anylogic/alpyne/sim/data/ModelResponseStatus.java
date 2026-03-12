package com.anylogic.alpyne.sim.data;

import com.anylogic.alpyne.JsonUtils;
import com.anylogic.alpyne.sim.AlpyneReinforcementLearningPlatform;
import com.anylogic.alpyne.sim.ModelManager;
import com.anylogic.engine.Agent;
import com.anylogic.engine.Engine;
import com.anylogic.engine.Engine.State;
import com.anylogic.rl.data.Action;
import com.anylogic.rl.data.Configuration;
import com.anylogic.rl.data.Observation;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.Date;

public class ModelResponseStatus extends ModelResponse {
   public final State state;
   public final double time;
   public final Date date;
   public final double progress;
   public final boolean stop;
   public final Observation observation;
   @JsonProperty("sequence_id")
   public final int sequenceId;
   @JsonProperty("episode_num")
   public final int episodeNum;
   @JsonProperty("step_num")
   public final int stepNum;

   public ModelResponseStatus(AlpyneReinforcementLearningPlatform<Agent, Observation, Action, Configuration> platform) {
      super(true, platform.getLastTerminalStatusMessage());
      Engine e = platform.getEngine();
      if (e == null) {
         this.state = null;
         this.time = -1.0;
         this.date = null;
         this.progress = -1.0;
      } else {
         this.state = e.getState();
         this.time = e.time();
         this.date = e.date();
         this.progress = e.getProgress();
      }

      if (this.state != null && !this.state.equals(State.IDLE)) {
         this.stop = platform.checkStopCondition();
         this.observation = platform.getObservation();
      } else {
         this.stop = false;
         this.observation = ModelManager.getModelManager().getDescriptor().getObservationTemplate();
      }

      this.sequenceId = platform.getSequenceId();
      this.episodeNum = platform.getEpisode();
      this.stepNum = platform.getStep();
   }

   @Override
   public String toString() {
      StringBuilder builder = new StringBuilder();
      builder.append("ModelResponseStatus(").append(this.successful ? "SUCCESS" : "FAILURE").append(")");
      if (this.message != null) {
         builder.append(": ").append(this.message);
      }

      builder.append(" -> ").append(JsonUtils.toJson(this));
      return builder.toString();
   }
}
