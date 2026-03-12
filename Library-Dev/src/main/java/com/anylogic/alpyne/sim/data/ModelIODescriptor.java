package com.anylogic.alpyne.sim.data;

import com.anylogic.alpyne.JsonUtils;
import com.anylogic.engine.Agent;
import com.anylogic.engine.Engine;
import com.anylogic.engine.ExperimentReinforcementLearning;
import com.anylogic.engine.ReinforcementLearningDataAccessor;
import com.anylogic.engine.Engine.State;
import com.anylogic.rl.data.Action;
import com.anylogic.rl.data.Configuration;
import com.anylogic.rl.data.Observation;
import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.PrintWriter;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Date;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class ModelIODescriptor {
    private static final Logger log = LoggerFactory.getLogger(ModelIODescriptor.class);
    private List<ModelData> inputs;
    private List<ModelData> outputs;
    private EngineSettings engineSettingsTemplate;
    @JsonProperty("engine_settings")
    private List<ModelData> engineSettings;
    private List<ModelData> configuration;
    private List<ModelData> observation;
    private List<ModelData> action;
    @JsonIgnore
    private final ExperimentReinforcementLearning<Agent, Observation, Action, Configuration> experiment;
    @JsonIgnore
    private final Path rawScanLogPath;
    @JsonIgnore
    private Agent rootAgent;

    public ModelIODescriptor(
       ExperimentReinforcementLearning<Agent, Observation, Action, Configuration> experiment, Path rawScanLogPath
    ) {
       this.experiment = experiment;
       this.rawScanLogPath = rawScanLogPath;
       this.load();
    }

    private static List<ModelData> describeFields(Object obj) {
       return (List<ModelData>)(obj == null ? new ArrayList<>() : Arrays.stream(obj.getClass().getFields()).map(field -> {
          try {
             return new ModelData(field.getName(), field.getType().getSimpleName(), field.get(obj));
          } catch (Exception var3) {
             return null;
          }
       }).filter(Objects::nonNull).collect(Collectors.toUnmodifiableList()));
    }

    private Class<?> discoverType(Agent owner, String fieldName) {
       try {
          return owner.getClass().getField(fieldName).getType();
       } catch (NoSuchFieldException var4) {
          return null;
       }
    }

    private ModelData describeParameter(Agent root, String name) {
       try {
          Field paramField = root.getClass().getField(name);
          Object paramObject = paramField.get(root);
          String typeName = null;
          Object defaultValue = null;

          defaultValue = root.getParameter(name);
          if (paramObject != null && paramObject.getClass().getSimpleName().contains("Parameter")) {
             typeName = paramField.getGenericType().getTypeName().replaceAll("java\\.lang\\.", "");
             try {
                Method getDefaultValueMethod = paramObject.getClass().getMethod("getDefaultValue");
                defaultValue = getDefaultValueMethod.invoke(paramObject);
             } catch (Exception var13) {
                log.trace("Default value method not found for parameter {}: {}", name, var13.getMessage());
             }
          } else {
             typeName = paramField.getType().getSimpleName();
          }
          return new ModelData(name, typeName == null ? "N/A" : typeName, defaultValue);
       } catch (Exception var14) {
          log.warn("Failed to perform deep reflection on parameter '{}'. Falling back to simple discovery.", name, var14);
          return new ModelData(name, this.discoverType(root, name), root.getParameter(name));
       }
    }

    private void load() {
       log.info("Loading from experiment...");
       Agent root = this.experiment.createModel();
       try {
          this.load(root);
       } finally {
          Engine engine = root.getEngine();
          if (engine.getState() == State.IDLE) {
             engine.start(root);
             engine.stop();
          }
       }
    }

    private void load(Agent root) {
       long startTime = System.currentTimeMillis();
       log.info("Starting model inspection...");

       // Store root agent for later use in JSON export
       this.rootAgent = root;

       EngineSettings settingsObj = EngineSettings.fillFrom(root.getEngine());
       this.engineSettingsTemplate = settingsObj;
       this.engineSettings = Stream.of(
             new ModelData("units", settingsObj.getUnits()),
             new ModelData("start_time", settingsObj.getStartTime()),
             new ModelData("start_date", settingsObj.getStartDate()),
             new ModelData("stop_time", settingsObj.getStopTime()),
             new ModelData("stop_date", Date.class.getSimpleName(), settingsObj.getStopDate()),
             new ModelData("seed", long.class.getSimpleName(), settingsObj.getSeed())
          )
          .collect(Collectors.toUnmodifiableList());
       this.inputs = Arrays.stream(root.getParameterNames()).map(name -> this.describeParameter(root, name)).collect(Collectors.toUnmodifiableList());
       List<ModelData> allOutputs = new ArrayList<>();
       try {
          log.info("Starting intelligent reflection scan of user-defined model elements...");
          String rootPackageName = root.getClass().getPackageName();
          this.recursiveDiscover(root, "root", allOutputs, new HashSet<>(), rootPackageName);
          log.info("Finished intelligent reflection scan.");
       } catch (Throwable var9) {
          log.error("A critical error occurred during recursive discovery.", var9);
       }
       this.outputs = allOutputs.stream().distinct().collect(Collectors.toList());
       ReinforcementLearningDataAccessor<Agent, Observation, Action, Configuration> dataAccessor = this.experiment.getDataAccessor();
       this.configuration = describeFields(dataAccessor.createConfiguration());
       this.observation = describeFields(dataAccessor.createObservation());
       this.action = describeFields(dataAccessor.createAction());
       this.writeRawScanLog();
       this.exportStructuredJSON();
       long endTime = System.currentTimeMillis();
       log.info("Model inspection finished in {} ms. Found {} user-defined elements.", endTime - startTime, this.outputs.size());
    }

    private void recursiveDiscover(Object obj, String prefix, List<ModelData> outputs, Set<Object> visited, String rootPackageName) {
       if (obj != null && !visited.contains(obj)) {
          visited.add(obj);
          Class<?> objClass = obj.getClass();
          if (objClass.getPackageName().startsWith(rootPackageName)) {
             for (Field field : objClass.getDeclaredFields()) {
                if (Modifier.isPublic(field.getModifiers())) {
                   try {
                      String fullName = prefix + "." + field.getName();
                      String typeName = field.getGenericType().getTypeName().replaceAll("java\\.lang\\.", "");
                      outputs.add(new ModelData(fullName, "FIELD: " + typeName, null));
                      Object fieldValue = field.get(obj);
                      this.recursiveDiscover(fieldValue, fullName, outputs, visited, rootPackageName);
                   } catch (Exception var15) {}
                }
             }
             Set<String> ignoreMethods = new HashSet<>(Arrays.asList("toString", "hashCode", "getClass", "notify", "notifyAll", "wait", "equals"));
             for (Method method : objClass.getDeclaredMethods()) {
                if (Modifier.isPublic(method.getModifiers()) && method.getParameterCount() == 0 && !method.getReturnType().equals(void.class) && !ignoreMethods.contains(method.getName())) {
                   try {
                      String fullName = prefix + "." + method.getName() + "()";
                      String returnTypeName = method.getGenericReturnType().getTypeName().replaceAll("java\\.lang\\.", "");
                      outputs.add(new ModelData(fullName, "METHOD: " + returnTypeName, null));
                   } catch (Exception var14) {}
                }
             }
          }
       }
    }

    private void writeRawScanLog() {
       if (this.rawScanLogPath != null) {
          System.out.println("Writing raw scan results to: " + this.rawScanLogPath);
          try (PrintWriter writer = new PrintWriter(this.rawScanLogPath.toFile(), StandardCharsets.UTF_8)) {
             writer.println("--- Discovered User-Defined Model Elements (Including Parameter Metadata) ---");
             writer.println("\n--- Inputs (Parameters) ---");
             writer.println(String.format("%-40s | %s", "Parameter Name", "Type/Default Value"));
             writer.println("-".repeat(80));
             for (ModelData data : this.inputs) {
                String meta = String.format("Type: %s, Default: %s", data.type, data.value);
                writer.println(String.format("%-40s | %s", data.name, meta));
             }
             writer.println("\n--- Outputs (Fields/Methods) ---");
             writer.println(String.format("%-80s | %s", "Element Path", "Data Type"));
             writer.println("-".repeat(80));
             for (ModelData data : this.outputs) {
                writer.println(String.format("%-80s | %s", data.name, data.type));
             }
             writer.println("\n--- Other Descriptions (Configuration, Observation, Action) ---");
             writer.println("Configuration: " + this.configuration.stream().map(d -> d.name).collect(Collectors.joining(", ")));
             writer.println("Observation: " + this.observation.stream().map(d -> d.name).collect(Collectors.joining(", ")));
             writer.println("Action: " + this.action.stream().map(d -> d.name).collect(Collectors.joining(", ")));
          } catch (Exception var7) {
             System.err.println("Failed to write raw scan log: " + var7.getMessage());
             var7.printStackTrace(System.err);
          }
       }
    }
    
    /**
     * Export a structured JSON file containing all discovered model elements
     * with intelligent categorization and suggested bounds.
     */
    private void exportStructuredJSON() {
        if (this.rawScanLogPath == null) {
            log.warn("Cannot export structured JSON: rawScanLogPath is null");
            return;
        }

        try {
            // Construct output path (same directory as raw log)
            Path outputPath = this.rawScanLogPath.getParent().resolve("structured_scan_results.json");
            log.info("Exporting structured JSON to: {}", outputPath);

            ObjectMapper mapper = new ObjectMapper();
            mapper.enable(SerializationFeature.INDENT_OUTPUT);

            // Create root JSON object
            ObjectNode root = mapper.createObjectNode();
            root.put("scan_timestamp", Instant.now().toString());
            root.put("model_name", this.rootAgent.getClass().getSimpleName());

            // Create variables array
            ArrayNode variablesArray = mapper.createArrayNode();

            // Get current RL experiment state
            Set<String> currentConfigNames = this.configuration.stream()
                .map(d -> d.name)
                .collect(Collectors.toSet());
            Set<String> currentObsNames = this.observation.stream()
                .map(d -> d.name)
                .collect(Collectors.toSet());
            Set<String> currentActionNames = this.action.stream()
                .map(d -> d.name)
                .collect(Collectors.toSet());

            // Process input parameters
            for (ModelData input : this.inputs) {
                ObjectNode varNode = mapper.createObjectNode();
                varNode.put("name", input.name);
                varNode.put("category", "parameter");
                varNode.put("data_type", input.type);

                // Add default value
                if (input.value != null) {
                    varNode.put("default_value", input.value.toString());
                } else {
                    varNode.putNull("default_value");
                }

                varNode.put("path", "root." + input.name);

                // Check if currently in RL experiment
                boolean isInRLExp = currentConfigNames.contains(input.name) ||
                                   currentObsNames.contains(input.name) ||
                                   currentActionNames.contains(input.name);
                varNode.put("is_currently_in_rl_experiment", isInRLExp);

                if (isInRLExp) {
                    ArrayNode currentlyUsedAs = mapper.createArrayNode();
                    if (currentConfigNames.contains(input.name)) currentlyUsedAs.add("configuration");
                    if (currentObsNames.contains(input.name)) currentlyUsedAs.add("observation");
                    if (currentActionNames.contains(input.name)) currentlyUsedAs.add("action");
                    varNode.set("currently_used_as", currentlyUsedAs);
                }

                // Suggest usage
                ArrayNode suggestedAs = mapper.createArrayNode();
                suggestedAs.add("action");
                suggestedAs.add("observation");
                suggestedAs.add("configuration");
                varNode.set("suggested_as", suggestedAs);

                // Calculate intelligent bounds based on type and default value
                ObjectNode bounds = mapper.createObjectNode();
                String typeClean = input.type.replaceAll("<.*>", "").trim();

                try {
                    if (typeClean.equals("double") || typeClean.equals("Double")) {
                        double defaultVal = input.value != null ? Double.parseDouble(input.value.toString()) : 0.0;
                        if (defaultVal > 0) {
                            bounds.put("suggested_min", defaultVal * 0.5);
                            bounds.put("suggested_max", defaultVal * 2.0);
                        } else if (defaultVal < 0) {
                            bounds.put("suggested_min", defaultVal * 2.0);
                            bounds.put("suggested_max", defaultVal * 0.5);
                        } else {
                            bounds.put("suggested_min", 0.0);
                            bounds.put("suggested_max", 100.0);
                        }
                    } else if (typeClean.equals("int") || typeClean.equals("Integer")) {
                        int defaultVal = input.value != null ? Integer.parseInt(input.value.toString()) : 0;
                        bounds.put("suggested_min", Math.max(0, defaultVal - 10));
                        bounds.put("suggested_max", defaultVal + 10);
                    } else if (typeClean.equals("boolean") || typeClean.equals("Boolean")) {
                        bounds.put("suggested_min", 0);
                        bounds.put("suggested_max", 1);
                    } else {
                        bounds.put("suggested_min", 0);
                        bounds.put("suggested_max", 100);
                    }
                } catch (Exception e) {
                    log.warn("Failed to parse default value for {}: {}", input.name, e.getMessage());
                    bounds.put("suggested_min", 0);
                    bounds.put("suggested_max", 100);
                }

                varNode.set("bounds", bounds);
                variablesArray.add(varNode);
            }

            // Process current observations
            for (ModelData obs : this.observation) {
                ObjectNode varNode = mapper.createObjectNode();
                varNode.put("name", obs.name);
                varNode.put("category", "observation");
                varNode.put("data_type", obs.type);
                varNode.putNull("default_value");

                // Try to find the path from outputs
                String path = this.findPathForVariable(obs.name);
                varNode.put("path", path != null ? path : "root." + obs.name);

                varNode.put("is_currently_in_rl_experiment", true);

                ArrayNode currentlyUsedAs = mapper.createArrayNode();
                currentlyUsedAs.add("observation");
                varNode.set("currently_used_as", currentlyUsedAs);

                ArrayNode suggestedAs = mapper.createArrayNode();
                suggestedAs.add("observation");
                varNode.set("suggested_as", suggestedAs);

                // Set reasonable bounds for observations
                ObjectNode bounds = mapper.createObjectNode();
                String typeClean = obs.type.replaceAll("<.*>", "").trim();

                if (typeClean.equals("double") || typeClean.equals("Double")) {
                    // Check if it's a utilization metric (typically 0-1)
                    if (obs.name.toLowerCase().contains("utilization") ||
                        obs.name.toLowerCase().contains("rate")) {
                        bounds.put("suggested_min", 0.0);
                        bounds.put("suggested_max", 1.0);
                    } else {
                        bounds.put("suggested_min", 0.0);
                        bounds.put("suggested_max", 1000.0);
                    }
                } else if (typeClean.equals("int") || typeClean.equals("Integer")) {
                    bounds.put("suggested_min", 0);
                    bounds.put("suggested_max", 10000);
                } else {
                    bounds.put("suggested_min", 0);
                    bounds.put("suggested_max", 100);
                }

                varNode.set("bounds", bounds);
                variablesArray.add(varNode);
            }

            // Process current actions
            for (ModelData act : this.action) {
                // Skip if already added as parameter
                boolean alreadyAdded = this.inputs.stream()
                    .anyMatch(inp -> inp.name.equals(act.name));
                if (alreadyAdded) continue;

                ObjectNode varNode = mapper.createObjectNode();
                varNode.put("name", act.name);
                varNode.put("category", "action");
                varNode.put("data_type", act.type);
                varNode.putNull("default_value");
                varNode.put("path", "root." + act.name);

                varNode.put("is_currently_in_rl_experiment", true);

                ArrayNode currentlyUsedAs = mapper.createArrayNode();
                currentlyUsedAs.add("action");
                varNode.set("currently_used_as", currentlyUsedAs);

                ArrayNode suggestedAs = mapper.createArrayNode();
                suggestedAs.add("action");
                varNode.set("suggested_as", suggestedAs);

                // Set reasonable bounds for actions
                ObjectNode bounds = mapper.createObjectNode();
                String typeClean = act.type.replaceAll("<.*>", "").trim();

                if (typeClean.equals("double") || typeClean.equals("Double")) {
                    bounds.put("suggested_min", 0.0);
                    bounds.put("suggested_max", 200.0);
                } else if (typeClean.equals("int") || typeClean.equals("Integer")) {
                    bounds.put("suggested_min", 0);
                    bounds.put("suggested_max", 100);
                } else {
                    bounds.put("suggested_min", 0);
                    bounds.put("suggested_max", 100);
                }

                varNode.set("bounds", bounds);
                variablesArray.add(varNode);
            }

            root.set("variables", variablesArray);

            // Add current RL experiment state summary
            ObjectNode rlState = mapper.createObjectNode();
            ArrayNode configArray = mapper.createArrayNode();
            this.configuration.forEach(d -> configArray.add(d.name));
            rlState.set("configuration", configArray);

            ArrayNode obsArray = mapper.createArrayNode();
            this.observation.forEach(d -> obsArray.add(d.name));
            rlState.set("observations", obsArray);

            ArrayNode actArray = mapper.createArrayNode();
            this.action.forEach(d -> actArray.add(d.name));
            rlState.set("actions", actArray);

            root.set("rl_experiment_current_state", rlState);

            // Write to file
            Files.write(outputPath, mapper.writeValueAsBytes(root));
            log.info("Successfully exported structured JSON with {} variables", variablesArray.size());

        } catch (Exception e) {
            log.error("Failed to export structured JSON", e);
            System.err.println("Failed to export structured JSON: " + e.getMessage());
            e.printStackTrace(System.err);
        }
    }

    /**
     * Helper method to find the full path of a variable in the outputs list.
     */
    private String findPathForVariable(String varName) {
        for (ModelData output : this.outputs) {
            String path = output.name;
            // Extract the last part of the path
            String lastPart = path.substring(path.lastIndexOf('.') + 1);
            // Remove () if it's a method
            lastPart = lastPart.replace("()", "");

            if (lastPart.equals(varName) || lastPart.equals(varName.replace("o_", ""))) {
                return path;
            }
        }
        return null;
    }
    @JsonProperty("inputs")
    public List<ModelData> getInputsDescription() { return this.inputs; }
    
    @JsonProperty("outputs")
    public List<ModelData> getOutputsDescription() { return this.outputs; }
    
    @JsonProperty("engineSettings")
    public List<ModelData> getEngineSettingsDescription() { return this.engineSettings; }
    
    @JsonIgnore
    public EngineSettings getEngineSettingsTemplate() { return EngineSettings.copyOf(this.engineSettingsTemplate); }
    
    @JsonProperty("configuration")
    public List<ModelData> getConfigurationDescription() { return this.configuration; }
    @JsonIgnore
    public Class<?> getConfigurationType() { return ((Configuration)this.experiment.getDataAccessor().createConfiguration()).getClass(); }
    
    @JsonProperty("observation")
    public List<ModelData> getObservationDescription() { return this.observation; }
    
    @JsonIgnore
    public Observation getObservationTemplate() { return (Observation)this.experiment.getDataAccessor().createObservation(); }
    
    @JsonIgnore
    public Class<?> getObservationType() { return this.getObservationTemplate().getClass(); }
    
    @JsonProperty("action")
    public List<ModelData> getActionDescription() { return this.action; }
    
    @JsonIgnore
    public Class<?> getActionType() { return ((Action)this.experiment.getDataAccessor().createAction()).getClass(); }
}

