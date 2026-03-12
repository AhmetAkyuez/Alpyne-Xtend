package com.anylogic.alpyne.sim;

import com.anylogic.alpyne.JsonUtils;
import com.anylogic.alpyne.sim.api.JarReader;
import com.anylogic.alpyne.sim.data.ModelData;
import com.anylogic.alpyne.sim.data.ModelIODescriptor;
import com.anylogic.alpyne.sim.data.ModelRequest;
import com.anylogic.alpyne.sim.data.ModelRequestOutput;
import com.anylogic.alpyne.sim.data.ModelResponse;
import com.anylogic.alpyne.sim.data.ModelResponseEngineStatus;
import com.anylogic.alpyne.sim.data.ModelResponseNoBody;
import com.anylogic.alpyne.sim.data.ModelResponseOutputs;
import com.anylogic.alpyne.sim.data.ModelResponseStatus;
import com.anylogic.alpyne.sim.data.RequestArgumentValidator;
import com.anylogic.alpyne.sim.data.RequestResponse;
import com.anylogic.alpyne.sim.data.ResponseReason;
import com.anylogic.engine.Agent;
import com.anylogic.engine.ExperimentReinforcementLearning;
import com.anylogic.engine.Engine.State;
import com.anylogic.rl.data.Action;
import com.anylogic.rl.data.Configuration;
import com.anylogic.rl.data.Observation;
import com.networknt.schema.ValidationMessage;
import java.lang.reflect.Constructor;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingQueue;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class ModelManager {
    private static final Logger log = LoggerFactory.getLogger(ModelManager.class);
    private static ModelManager instance;
    private static long lockSleepTime = 10L;
    static boolean autoFinish = false;
    private ModelIODescriptor descriptor;
    private RequestArgumentValidator validator;
    private AlpyneReinforcementLearningPlatform<Agent, Observation, Action, Configuration> platform;
    ExperimentReinforcementLearning<Agent, Observation, Action, Configuration> experiment;
    private final BlockingQueue<ModelRequest> requestQueue = new LinkedBlockingQueue<>();
    private final ExecutorService executorService;
    private Future<?> future;

    public static ModelManager setup(String jar) {
       return setup(jar, lockSleepTime, false, null, null);
    }

    public static ModelManager setup(Class<?> expClass) {
       return setup(expClass, lockSleepTime, false, null, null);
    }

    public static ModelManager setup(String jar, long lockSleepTime, boolean autoFinish) {
       return setup(jar, lockSleepTime, autoFinish, null, null);
    }

    public static ModelManager setup(String jar, long lockSleepTime, boolean autoFinish, Path rawScanLogPath, Path structuredScanLogPath) {
       return setup(JarReader.findRLExperiment(jar), lockSleepTime, autoFinish, rawScanLogPath, structuredScanLogPath);
    }

    public static ModelManager setup(Class<?> expClass, long lockSleepTime, boolean autoFinish) {
       return setup(expClass, lockSleepTime, autoFinish, null, null);
    }

    public static ModelManager setup(Class<?> expClass, long lockSleepTime, boolean autoFinish, Path rawScanLogPath, Path structuredScanLogPath) {
       ModelManager.lockSleepTime = lockSleepTime;
       ModelManager.autoFinish = autoFinish;
       if (instance == null) {
           try {
               instance = new ModelManager(expClass, rawScanLogPath);
           } catch (Exception var7) {
               log.error("Failed to create modman", var7);
               throw new RuntimeException(var7);
           }

           return instance;
       } else {
           throw new RuntimeException("Can only setup the modman once.");
       }
    }

    public static ModelManager getModelManager() {
       return instance;
    }

    private ModelManager(Class<?> expClass, Path rawScanLogPath) throws Exception {
       log.trace("Booting up manager");
       long startMS = System.currentTimeMillis();
       this.experiment = createRLExperiment(expClass);
       this.descriptor = new ModelIODescriptor(this.experiment, rawScanLogPath);
       this.validator = new RequestArgumentValidator(this.experiment, this.descriptor);
       this.executorService = Executors.newSingleThreadExecutor();

       try {
           this.platform = new AlpyneReinforcementLearningPlatform<>(null);
           this.platform.setRequestQueue(this.requestQueue);
       } catch (Exception var7) {
           log.error("Problem creating platform", var7);
           return;
       }

       this.future = this.executorService.submit(() -> this.platform.run(this.experiment));
       log.trace("Creation time: {}", System.currentTimeMillis() - startMS);
    }

    public static <R extends Agent, O extends Observation, A extends Action, C extends Configuration> ExperimentReinforcementLearning<R, O, A, C> createRLExperiment(
       Class<?> expClass
    ) throws Exception {
       if (!ExperimentReinforcementLearning.class.isAssignableFrom(expClass)) {
           throw new RuntimeException(String.format("%s is not an ExperimentReinforcementLearning class", expClass));
       } else {
           Constructor<?> expConstructor = expClass.getDeclaredConstructor();
           log.info(String.format("Class [%s], calling constructor = [%s]", expClass, expConstructor));
           return (ExperimentReinforcementLearning<R, O, A, C>)expConstructor.newInstance();
       }
    }

    public ModelResponse execute(ModelRequest request) throws InterruptedException {
       if (!this.isDead() && this.platform.isActiveExperiment()) {
           Set<ValidationMessage> errors = this.validator.validate(request);
           if (!errors.isEmpty()) {
               return new ModelResponseNoBody(ResponseReason.INVALID_REQUEST, errors.toString());
           } else {
               return (ModelResponse)(switch (request.type) {
                   case OUTPUT -> {
                       Set<String> desiredNames = Set.of(((ModelRequestOutput)request).names);
                       yield new ModelResponseOutputs(
                           this.descriptor
                               .getOutputsDescription()
                               .stream()
                               .filter(md -> desiredNames.contains(md.name))
                               .map(md -> new ModelData(md.name, md.type, this.platform.getFieldValue(md.name)))
                               .toArray(ModelData[]::new)
                       );
                   }
                   case STATUS -> new ModelResponseStatus(this.platform);
                   case ENGINE_STATUS -> new ModelResponseEngineStatus(this.platform);
                   default -> {
                       this.requestQueue.put(request);
                       yield new ModelResponseNoBody(ResponseReason.SUCCESS, String.valueOf(this.requestQueue.size()));
                   }
               });
           }
       } else {
           return new ModelResponseNoBody(ResponseReason.MODEL_DEAD, "If unexpected, check the logs");
       }
    }

    public boolean isDead() {
       return this.isDestructed() || this.platform == null;
    }

    public boolean isDestructed() {
       return this.executorService.isShutdown() && this.executorService.isTerminated();
    }

    public RequestResponse<Map<String, ?>> selfDestruct() {
       log.trace("Attempting to self destruct");
       long startMS = System.currentTimeMillis();
       if (this.future != null) {
           this.future.cancel(true);
       }

       this.executorService.shutdownNow();
       RequestResponse<Map<String, ?>> rr = new RequestResponse<>(true, Map.of("is_alive", !this.executorService.isShutdown()), ResponseReason.SUCCESS);
       log.debug("Self-destructed in {} ms; returning response: {}", System.currentTimeMillis() - startMS, JsonUtils.toJson(rr));
       return rr;
    }

    public static boolean lockUntilEngineStateCondition(List<String> states, int timeoutMS) throws IllegalArgumentException {
       return lockUntilEngineStateCondition(states, null, timeoutMS);
    }

    public static boolean lockUntilEngineStateCondition(List<String> states, Integer minSequenceIdToSkip, int timeoutMS) throws IllegalArgumentException {
       State[] acceptedStates;
       if (states != null && !states.isEmpty()) {
           acceptedStates = states.stream().map(State::valueOf).toArray(State[]::new);
       } else {
           acceptedStates = Arrays.stream(State.values()).toArray(State[]::new);
       }

       boolean inState = false;
       boolean timedOut = false;
       long timeStartedLock = System.currentTimeMillis();

       do {
           try {
               Thread.sleep(lockSleepTime);
               inState = Arrays.stream(acceptedStates).anyMatch(s -> s == getModelManager().getPlatform().getEngineState())
                   && (minSequenceIdToSkip == null || getModelManager().getPlatform().getSequenceId() >= minSequenceIdToSkip);
               timedOut = System.currentTimeMillis() - timeStartedLock >= timeoutMS;
           } catch (InterruptedException var9) {
               throw new RuntimeException(var9);
           }
       } while (!inState && !timedOut);

       return inState;
    }

    public ModelIODescriptor getDescriptor() {
       return this.descriptor;
    }

    public RequestArgumentValidator getValidator() {
       return this.validator;
    }

    public AlpyneReinforcementLearningPlatform<Agent, Observation, Action, Configuration> getPlatform() {
       return this.platform;
    }
}

