package com.anylogic.alpyne.sim.data;

import com.anylogic.alpyne.JsonUtils;
import com.anylogic.engine.Agent;
import com.anylogic.engine.ExperimentReinforcementLearning;
import com.anylogic.rl.data.Action;
import com.anylogic.rl.data.Configuration;
import com.anylogic.rl.data.Observation;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;
import com.github.victools.jsonschema.generator.OptionPreset;
import com.github.victools.jsonschema.generator.SchemaGenerator;
import com.github.victools.jsonschema.generator.SchemaGeneratorConfigBuilder;
import com.github.victools.jsonschema.generator.SchemaVersion;
import com.networknt.schema.JsonSchema;
import com.networknt.schema.JsonSchemaFactory;
import com.networknt.schema.ValidationMessage;
import com.networknt.schema.SpecVersion.VersionFlag;
import com.networknt.schema.ValidationMessage.Builder;
import java.lang.reflect.Type;
import java.util.HashSet;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class RequestArgumentValidator<C extends Configuration, A extends Action> {
   private static final Logger log = LoggerFactory.getLogger(RequestArgumentValidator.class);
   private JsonSchema resetSchema;
   private JsonSchema stepSchema;
   private JsonSchema outputSchema;

   public RequestArgumentValidator(ExperimentReinforcementLearning<Agent, Observation, A, C> experiment, ModelIODescriptor descriptor) {
      this.load(experiment, descriptor);
   }

   private void load(ExperimentReinforcementLearning<Agent, Observation, A, C> experiment, ModelIODescriptor descriptor) {
      C config = (C)experiment.getDataAccessor().createConfiguration();
      ModelRequestReset<C> reset = new ModelRequestReset<>(config, descriptor.getEngineSettingsTemplate());
      SchemaGeneratorConfigBuilder resetCfgBuilder = new SchemaGeneratorConfigBuilder(SchemaVersion.DRAFT_2020_12, OptionPreset.PLAIN_JSON);
      resetCfgBuilder.forFields()
         .withPropertyNameOverrideResolver(
            field -> Optional.ofNullable((JsonProperty)field.getAnnotationConsideringFieldAndGetter(JsonProperty.class))
               .<String>map(JsonProperty::value)
               .orElse(null)
         )
         .withRequiredCheck(f -> !f.getName().equals("type"))
         .withNullableCheck(f -> true)
         .withTargetTypeOverridesResolver(
            f -> Optional.ofNullable((EngineSettings.ValidOneOfTypes)f.getAnnotationConsideringFieldAndGetterIfSupported(EngineSettings.ValidOneOfTypes.class))
               .map(EngineSettings.ValidOneOfTypes::value)
               .map(Stream::of)
               .map(stream -> stream.map(specificSubtype -> f.getContext().resolve(specificSubtype, new Type[0])))
               .map(stream -> stream.collect(Collectors.toList()))
               .orElse(null)
         );
      SchemaGenerator resetSchemaGen = new SchemaGenerator(resetCfgBuilder.build());
      this.resetSchema = JsonSchemaFactory.getInstance(VersionFlag.V202012)
         .getSchema(resetSchemaGen.generateSchema(reset.getClass(), new Type[]{config.getClass()}));
      log.info("RESET SCHEMA:\n{}", this.resetSchema);
      A action = (A)experiment.getDataAccessor().createAction();
      ModelRequestStep<A> step = new ModelRequestStep<>(action);
      SchemaGeneratorConfigBuilder stepCfgBuilder = new SchemaGeneratorConfigBuilder(SchemaVersion.DRAFT_2020_12, OptionPreset.PLAIN_JSON);
      stepCfgBuilder.forFields().withRequiredCheck(f -> !f.getName().equals("type"));
      SchemaGenerator stepSchemaGen = new SchemaGenerator(stepCfgBuilder.build());
      this.stepSchema = JsonSchemaFactory.getInstance(VersionFlag.V202012)
         .getSchema(stepSchemaGen.generateSchema(step.getClass(), new Type[]{action.getClass()}));
      log.info("STEP SCHEMA:\n{}", this.stepSchema);
      String[] names = descriptor.getOutputsDescription().stream().map(data -> data.name).toArray(String[]::new);
      String pattern = String.join("|", names);
      ModelRequestOutput output = new ModelRequestOutput(names);
      SchemaGeneratorConfigBuilder outputCfgBuilder = new SchemaGeneratorConfigBuilder(SchemaVersion.DRAFT_2020_12, OptionPreset.PLAIN_JSON);
      outputCfgBuilder.forFields()
         .withRequiredCheck(f -> !f.getName().equals("type"))
         .withStringPatternResolver(
            f -> f.getName().equals("names")
                  && f.getContext().getSimpleTypeDescription(f.getDeclaringType()).equals("ModelRequestOutput")
                  && f.isFakeContainerItemScope()
               ? pattern
               : null
         );
      SchemaGenerator outputSchemaGen = new SchemaGenerator(outputCfgBuilder.build());
      this.outputSchema = JsonSchemaFactory.getInstance(VersionFlag.V202012).getSchema(outputSchemaGen.generateSchema(output.getClass(), new Type[0]));
      log.info("OUTPUT SCHEMA:\n{}", this.outputSchema);
   }

   public Set<ValidationMessage> validate(ModelRequest request) {
      JsonNode node = JsonUtils.mapper.valueToTree(request);
      return this.validate(node, request.type);
   }

   private Set<ValidationMessage> validate(JsonNode node, RequestType type) {
      Set<ValidationMessage> messages = null;
      if (node != null && type != null) {
         switch (type) {
            case OUTPUT:
               messages = this.outputSchema.validate(node);
               break;
            case RESET:
               messages = this.resetSchema.validate(node);
               break;
            case STEP:
               messages = this.stepSchema.validate(node);
               break;
            case STATUS:
            case ENGINE_STATUS:
               messages = new HashSet<>();
         }
      } else {
         messages = new HashSet<>();
         if (node == null) {
            messages.add(new Builder().customMessage("Passed a null request node").build());
         }

         if (type == null) {
            messages.add(new Builder().customMessage("Passed a null request type").build());
         }
      }

      messages.forEach(msg -> log.warn("Failed to validate {} request: {}", type, msg));
      return messages;
   }

   public JsonSchema getResetSchema() {
      return this.resetSchema;
   }

   public JsonSchema getStepSchema() {
      return this.stepSchema;
   }

   public JsonSchema getOutputSchema() {
      return this.outputSchema;
   }
}
