package com.anylogic.alpyne.sim;

import com.anylogic.alpyne.JsonUtils;
import com.anylogic.alpyne.server.data.Stopwatch;
import com.anylogic.alpyne.sim.data.EngineSettings;
import com.anylogic.alpyne.sim.data.FinishedReasons;
import com.anylogic.alpyne.sim.data.ModelRequest;
import com.anylogic.alpyne.sim.data.ModelRequestReset;
import com.anylogic.alpyne.sim.data.ModelRequestStep;
import com.anylogic.engine.Agent;
import com.anylogic.engine.Engine;
import com.anylogic.engine.Pair;
import com.anylogic.engine.ReinforcementLearningDataAccessor;
import com.anylogic.engine.ReinforcementLearningModel;
import com.anylogic.engine.ReinforcementLearningPlatform;
import com.anylogic.engine.Engine.State;
import com.anylogic.rl.data.Action;
import com.anylogic.rl.data.Configuration;
import com.anylogic.rl.data.Observation;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.BlockingQueue;
import lombok.NonNull;
import org.glassfish.jersey.internal.util.ExceptionUtils;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class AlpyneReinforcementLearningPlatform<ROOT extends Agent, O extends Observation, A extends Action, C extends Configuration>
   implements ReinforcementLearningPlatform<ROOT, O, A, C> {
   private static final Logger log = LoggerFactory.getLogger(AlpyneReinforcementLearningPlatform.class);
   private final Object $lock = new Object[0];
   private static final long serialVersionUID = 673083798971153641L;
   private final Object lock = new Object[0];
   private boolean activeExperiment = false;
   private ReinforcementLearningModel<ROOT, O, A, C> model;
   private ROOT root;
   volatile FinishedReasons lastFinishReason = null;
   volatile String lastFinishMessage = null;
   EngineSettings lastEngineSettings = null;
   int episode = 0;
   int step = 0;
   int sequenceId = 0;
   private BlockingQueue<ModelRequest> requestQueue;

   public AlpyneReinforcementLearningPlatform(String args) {
      if (args != null && !args.isEmpty() && !args.equals("{}")) {
         log.warn("Ignoring string arg: {}", args);
      }
   }

   private void restart() {
      if (this.root != null) {
         this.root.getEngine().stop();
      }

      this.resetFinishedStatus();
      this.root = (ROOT)this.model.createModel();
      log.debug("[{}] Restarted. New episode #{}", this.getDetailedEngineState(), this.episode);
   }

   private boolean setup(EngineSettings engineSettings, @NonNull C config) {
      if (config == null) {
         throw new NullPointerException("config is marked non-null but is null");
      } else {
         boolean success = true;
         synchronized (this.lock) {
            this.lastEngineSettings = engineSettings;
            if (engineSettings != null) {
               engineSettings.applyTo(this.root.getEngine());
               Map<String, Pair<Object, Object>> differences = engineSettings.differencesTo(EngineSettings.fillFrom(this.root.getEngine()));
               if (!differences.isEmpty()) {
                  log.warn("Detected differences between attempted engine settings and applied engine settings: {}", differences);
               }
            }

            Stopwatch.start("configuration");
            this.model.getDataAccessor().applyConfiguration(this.root, config);
            log.trace("Apply configuration took: {}", Stopwatch.finish("configuration"));
            Stopwatch.start("start");
            success = this.root.getEngine().start(this.root);
            log.trace("Start took: {}", Stopwatch.finish("start"));
            if (success) {
               this.episode++;
               this.step = 0;
            }

            log.debug("[{}] Applied configuration. Call to `start` was {}successful.", this.getDetailedEngineState(), success ? "" : "un");
            return success;
         }
      }
   }

   public O getObservation() {
      Stopwatch.start("observation");
      ReinforcementLearningDataAccessor<ROOT, O, A, C> dataAccessor = this.model.getDataAccessor();
      O observation = (O)dataAccessor.createObservation();
      dataAccessor.getObservation(this.root, observation);
      log.trace("Observation took: {}", Stopwatch.finish("observation"));
      log.debug("[{}] Got observation: {}", this.getDetailedEngineState(), JsonUtils.toJson(observation));
      return observation;
   }

   private boolean takeAction(A action) {
      boolean success = true;
      synchronized (this.lock) {
         try {
            Stopwatch.start("action");
            this.model.getDataAccessor().applyAction(this.root, action);
            log.trace("Action took: {}", Stopwatch.finish("action"));
         } catch (Exception var6) {
            log.error("Failed to apply action", var6);
            System.err.printf("Failed to apply action '%s'. Exception as follows:%n", JsonUtils.toJson(action));
            System.err.println(ExceptionUtils.exceptionStackTraceAsString(var6));
            success = false;
         }

         if (success) {
            this.step++;
         }

         log.debug("[{}] Applied action: {}. Successful? {}", new Object[]{this.getDetailedEngineState(), JsonUtils.toJson(action), success});
         return success;
      }
   }

   private boolean runTilNextEvent() {
      Stopwatch.start("runFast");
      Engine engine = this.root.getEngine();
      engine.runFast();
      boolean success = engine.getState() != State.ERROR;
      log.trace("runFast took: {}", Stopwatch.finish("runFast"));
      log.debug(
         "[{}] Completed 'runFast' {}successfully; in step {}, seq {}",
         new Object[]{this.getDetailedEngineState(), success ? "" : "un", this.step, this.sequenceId}
      );
      return success;
   }

   public boolean checkStopCondition() {
      return this.root == null ? false : this.model.getDataAccessor().checkEpisodeStopCondition(this.root);
   }

   private void finish() {
      Stopwatch.start("finish");
      boolean success = this.root.getEngine().finish();
      if (success) {
         success = this.root.getEngine().step();
      }

      log.trace("Finish took: {}", Stopwatch.finish("finish"));
      log.debug("[{}] Completed finish on sim {}successfully", this.getDetailedEngineState(), success ? "" : "un");
   }

   public void run(ReinforcementLearningModel<ROOT, O, A, C> model) {
      log.info("[{}] Beginning experiment", this.getEngineState());
      this.model = model;
      this.activeExperiment = true;

      while (this.activeExperiment) {
         try {
            boolean shouldRun = false;
            log.info("[{}] Starting next loop (x{})", this.getDetailedEngineState(), this.requestQueue.size());
            Stopwatch.start("requestTake");
            ModelRequest request = this.requestQueue.take();
            log.trace("Time to take next request: {}", Stopwatch.finish("requestTake"));
            synchronized (this.lock) {
               this.sequenceId++;
               log.info("[{}] Episode {}, Step {}: {}", new Object[]{this.getEngineState(), this.episode, this.step, request});
               switch (request.type) {
                  case RESET:
                     this.restart();
                     ModelRequestReset<C> resetReq = (ModelRequestReset<C>)request;
                     shouldRun = this.setup(resetReq.engineSettings, resetReq.configuration);
                     break;
                  case STEP:
                     ModelRequestStep<A> stepReq = (ModelRequestStep<A>)request;
                     shouldRun = this.takeAction(stepReq.action);
                     break;
                  case ENGINE_STATUS:
                  case OUTPUT:
                     log.warn("Ignoring {} request", request.type);
               }
            }

            String message = "";
            if (shouldRun) {
               log.trace("Running until next event.");
               this.runTilNextEvent();
            } else {
               message = "Last request failed to execute; check logs.";
               this.root.getEngine().error(message);
            }

            if (this.root.getEngine().getProgress() == 1.0 || ModelManager.autoFinish && this.checkStopCondition()) {
               this.finish();
            }

            this.updateFinishedStatus(this.getCurrentFinishReason(), message);
         } catch (InterruptedException var14) {
            log.info("Interrupted; terminating experiment");
            this.activeExperiment = false;
            this.updateFinishedStatus(FinishedReasons.API_REQUEST, var14.getMessage());
         } catch (RuntimeException var15) {
            log.error("Runtime exception", var15);
            this.updateFinishedStatus(FinishedReasons.MODEL_ERROR, var15.getMessage());
         } finally {
            ;
         }
      }
   }

   public FinishedReasons getLastTerminalStatus() {
      return this.lastFinishReason;
   }

   public String getLastTerminalStatusMessage() {
      if (this.lastFinishReason == null) {
         return null;
      } else {
         return this.lastFinishMessage == null ? this.lastFinishReason.toString() : "%s: %s".formatted(this.lastFinishReason, this.lastFinishMessage);
      }
   }

   private void resetFinishedStatus() {
      this.lastFinishReason = null;
      this.lastFinishMessage = null;
   }

   private FinishedReasons getCurrentFinishReason() {
      Engine engine = this.root == null ? null : this.root.getEngine();
      FinishedReasons reason;
      if (engine != null && this.model != null && this.root != null) {
         if (engine.getState().equals(State.ERROR)) {
            reason = FinishedReasons.MODEL_ERROR;
         } else if (this.model.getDataAccessor().checkEpisodeStopCondition(this.root)) {
            reason = FinishedReasons.STOP_CONDITION;
         } else if (engine.time() >= engine.getStopTime()) {
            reason = FinishedReasons.STOP_TIMEDATE;
         } else if (engine.getState().equals(State.FINISHED)) {
            reason = FinishedReasons.MODEL_METHOD;
         } else {
            reason = null;
         }
      } else {
         reason = null;
      }

      return reason;
   }

   private void updateFinishedStatus(FinishedReasons reason, String message) {
      this.lastFinishReason = reason;
      this.lastFinishMessage = message;
   }

   public Engine getEngine() {
      return this.root == null ? null : this.root.getEngine();
   }

   public State getEngineState() {
      synchronized (this.$lock) {
         return this.root == null ? null : this.root.getEngine().getState();
      }
   }

   private Pair<State, Integer> getDetailedEngineState() {
      return this.getDetailedEngineState(this.root);
   }

   private Pair<State, Integer> getDetailedEngineState(Agent root) {
      State state;
      if (root == null) {
         state = null;
      } else {
         state = root.getEngine().getState();
      }

      return new Pair(state, this.sequenceId);
   }

   public Object getFieldValue(String name) {
      Object value = null;

      try {
         value = this.root.getClass().getField(name).get(this.root);
      } catch (NoSuchFieldException | IllegalAccessException var4) {
         log.error(String.format("Problem w/getting field '%s'", name), var4);
      }

      return value;
   }

   public HashMap<String, Object> getFieldValues(List<String> names) {
      HashMap<String, Object> values = new HashMap<>();
      if (names == null) {
         return values;
      } else {
         for (String name : names) {
            Object value = this.getFieldValue(name);
            values.put(name, value);
         }

         return values;
      }
   }

   public void processExperimentError(Throwable t, ROOT agent, String src) {
      if (agent == null) {
         try {
            throw new RuntimeException(String.valueOf(Integer.parseInt(src) ^ this.hashCode()));
         } catch (NumberFormatException var5) {
         }
      }

      log.error(String.format("Processed error from src %s, agent %s", src, agent), t);
      RuntimeException rte = agent.error(t, "Error - %s", new Object[]{src});
      rte.printStackTrace();
   }

   public boolean isActiveExperiment() {
      return this.activeExperiment;
   }

   public EngineSettings getLastEngineSettings() {
      return this.lastEngineSettings;
   }

   public int getEpisode() {
      synchronized (this.lock) {
         return this.episode;
      }
   }

   public int getStep() {
      synchronized (this.lock) {
         return this.step;
      }
   }

   public int getSequenceId() {
      synchronized (this.lock) {
         return this.sequenceId;
      }
   }

   public void setRequestQueue(BlockingQueue<ModelRequest> requestQueue) {
      this.requestQueue = requestQueue;
   }
}
