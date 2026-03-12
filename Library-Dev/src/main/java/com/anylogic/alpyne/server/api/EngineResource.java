package com.anylogic.alpyne.server.api;

import com.anylogic.alpyne.JsonUtils;
import com.anylogic.alpyne.server.data.ExpectationMismatch;
import com.anylogic.alpyne.server.data.ServerException;
import com.anylogic.alpyne.sim.ModelManager;
import com.anylogic.alpyne.sim.data.ModelRequestEngineStatus;
import com.anylogic.alpyne.sim.data.ModelRequestStatus;
import com.anylogic.alpyne.sim.data.ModelResponse;
import com.anylogic.engine.Engine.State;
import jakarta.inject.Inject;
import jakarta.inject.Singleton;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.QueryParam;
import jakarta.ws.rs.core.Response;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Path("/engine")
@Singleton
public class EngineResource {
   private static final Logger log = LoggerFactory.getLogger(EngineResource.class);
   @Inject
   ModelManager manager;

   @GET
   @Produces({"application/json"})
   public Response getEngineStatus() throws InterruptedException {
      log.trace("Getting engine status");
      long start = System.currentTimeMillis();
      ModelResponse modelResponse = this.manager.execute(new ModelRequestEngineStatus());
      Response response = Response.status(modelResponse.successful ? 200 : 500).entity(modelResponse).build();
      log.trace("[{}] Execution time: {}", response.getStatus(), System.currentTimeMillis() - start);
      return response;
   }

   @GET
   @Path("/lock")
   @Produces({"application/json"})
   public Response lockForEngineUpdate(@QueryParam("state") List<String> states, @QueryParam("timeout") int timeout) {
      log.trace("Locking for states {}, timeout {}", states, timeout);
      long start = System.currentTimeMillis();

      Response response;
      try {
         boolean inState = ModelManager.lockUntilEngineStateCondition(states, timeout);
         ModelResponse modelResponse = this.manager.execute(new ModelRequestStatus());
         if (modelResponse.successful) {
            response = Response.status(inState ? 200 : 408).entity(modelResponse).build();
         } else {
            response = Response.status(500, "Unable to get the status after waiting for the desired state(s)").entity(modelResponse).build();
         }
      } catch (IllegalArgumentException var8) {
         response = Response.status(422, "One or more of the provided states are invalid")
            .entity(new ServerException(new Exception(JsonUtils.toJson(new ExpectationMismatch(states, List.of(State.values()))))))
            .build();
      } catch (Exception var9) {
         log.trace(String.format("UNHANDLED EXCEPTION (%s)", var9.getClass()), var9);
         response = Response.status(500, "UNHANDLED EXCEPTION; SEE LOGS.").build();
      }

      log.trace("[{}] Execution time: {}", response.getStatus(), System.currentTimeMillis() - start);
      return response;
   }
}
