package com.anylogic.alpyne.server.api;

import com.anylogic.alpyne.JsonUtils;
import com.anylogic.alpyne.server.data.ExpectationMismatch;
import com.anylogic.alpyne.server.data.ServerException;
import com.anylogic.alpyne.sim.ModelManager;
import com.anylogic.alpyne.sim.data.ModelRequestReset;
import com.anylogic.alpyne.sim.data.ModelRequestStatus;
import com.anylogic.alpyne.sim.data.ModelRequestStep;
import com.anylogic.alpyne.sim.data.ModelResponse;
import com.anylogic.engine.Engine.State;
import com.fasterxml.jackson.core.JsonProcessingException;
import jakarta.inject.Inject;
import jakarta.inject.Singleton;
import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.PATCH;
import jakarta.ws.rs.PUT;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.Response;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Path("/rl")
@Singleton
public class RLResource {
   private static final Logger log = LoggerFactory.getLogger(RLResource.class);
   @Inject
   ModelManager manager;

   @GET
   @Produces({"application/json"})
   public Response rlQueryStatus() throws InterruptedException {
      log.trace("Querying status");
      long start = System.currentTimeMillis();
      ModelResponse modelResponse = this.manager.execute(new ModelRequestStatus());
      Response response = Response.status(modelResponse.successful ? 200 : 500).entity(modelResponse).build();
      log.trace("[{}] Execution time: {}", response.getStatus(), System.currentTimeMillis() - start);
      return response;
   }

   @PUT
   @Consumes({"application/json"})
   @Produces({"application/json"})
   public Response rlResetRun(String json) {
      log.trace("Resetting run with json {}", json);
      long start = System.currentTimeMillis();

      Response response;
      try {
         ModelRequestReset resetReq = JsonUtils.fromJson(json, ModelRequestReset.class);
         ModelResponse modelResponse = this.manager.execute(resetReq);
         if (modelResponse.successful) {
            response = Response.status(201).build();
         } else {
            response = Response.status(500, "Failed to send settings/configuration request")
               .entity(new ServerException(new Exception(modelResponse.toString())))
               .build();
         }
      } catch (JsonProcessingException var7) {
         log.error("JSON conversion failed", var7);
         response = Response.status(400, "JSON conversion failed").entity(new ServerException(var7)).build();
      } catch (Exception var8) {
         log.error(String.format("UNHANDLED EXCEPTION (%s)", var8.getClass()), var8);
         response = Response.status(500, "UNHANDLED EXCEPTION; SEE LOGS.").entity(new ServerException(var8)).build();
      }

      log.trace("[{}] Execution time: {}", response.getStatus(), System.currentTimeMillis() - start);
      return response;
   }

   @PATCH
   @Consumes({"application/json"})
   @Produces({"application/json"})
   public Response rlApplyStep(String json) {
      log.trace("Taking action with json {}", json);
      long start = System.currentTimeMillis();
      Response response;
      if (!this.manager.isDead() && this.manager.getPlatform().getEngineState().equals(State.PAUSED)) {
         try {
            ModelRequestStep stepReq = JsonUtils.fromJson(json, ModelRequestStep.class);
            ModelResponse modelResponse = this.manager.execute(stepReq);
            if (modelResponse.successful) {
               response = Response.status(202).build();
            } else {
               response = Response.status(500, "Failed to send step request").entity(new ServerException(new Exception(modelResponse.toString()))).build();
            }
         } catch (JsonProcessingException var7) {
            log.error("JSON conversion failed", var7);
            response = Response.status(400, "JSON conversion failed").entity(new ServerException(var7)).build();
         } catch (Exception var8) {
            log.error(String.format("UNHANDLED EXCEPTION (%s)", var8.getClass()), var8);
            response = Response.status(500, "UNHANDLED EXCEPTION; SEE LOGS.").entity(new ServerException(var8)).build();
         }
      } else {
         String reasonHelp = this.manager.isDead()
            ? "model dead"
            : String.format(
               "not in paused state (reason: %s)",
               this.manager.getPlatform().getLastTerminalStatus() == null
                  ? "UNKNOWN-CHECK LOGS"
                  : this.manager.getPlatform().getLastTerminalStatus().toString()
            );
         response = Response.status(409, String.format("Cannot take action; conflict with engine state: %s", reasonHelp))
            .entity(new ServerException(new Exception(JsonUtils.toJson(new ExpectationMismatch(this.manager.getPlatform().getEngineState(), State.PAUSED)))))
            .build();
      }

      log.trace("[{}] Execution time: {}", response.getStatus(), System.currentTimeMillis() - start);
      return response;
   }
}
