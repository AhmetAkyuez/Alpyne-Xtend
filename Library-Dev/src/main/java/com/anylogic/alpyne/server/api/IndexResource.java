package com.anylogic.alpyne.server.api;

import com.anylogic.alpyne.JsonUtils;
import com.anylogic.alpyne.server.data.EndpointScanner;
import com.anylogic.alpyne.server.data.ExpectationMismatch;
import com.anylogic.alpyne.server.data.ServerException;
import com.anylogic.alpyne.sim.ModelManager;
import com.anylogic.alpyne.sim.data.ModelRequestOutput;
import com.anylogic.alpyne.sim.data.ModelRequestStatus;
import com.anylogic.alpyne.sim.data.ModelResponse;
import com.anylogic.engine.Engine.State;
import jakarta.inject.Inject;
import jakarta.inject.Singleton;
import jakarta.ws.rs.DELETE;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.QueryParam;
import jakarta.ws.rs.core.Response;
import java.io.IOException;
import java.util.Comparator;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Path("/")
@Singleton
public class IndexResource {
   private static final Logger log = LoggerFactory.getLogger(IndexResource.class);
   @Inject
   ModelManager manager;

   @GET
   @Produces({"text/html"})
   public Response getDocumentation() throws IOException {
      StringBuilder sb = new StringBuilder();
      sb.append("<html><body>");
      sb.append("<h2>Auto-generated endpoint documentation</h2>");
      sb.append("<ul>");
      EndpointScanner.getEntries("com.anylogic.alpyne.server.api")
         .stream()
         .sorted(Comparator.comparing(EndpointScanner.EndpointEntry::getUrlEndpoint))
         .forEachOrdered(e -> sb.append("<li><pre>").append(e).append("</pre></li>"));
      sb.append("</ul>");
      sb.append("</body></html>");
      return Response.ok(sb.toString()).build();
   }

   @DELETE
   public Response shutdown() {
      log.trace("Shutdown triggered");
      this.manager.selfDestruct();
      return Response.accepted().build();
   }

   @GET
   @Path("/version")
   @Produces({"application/json"})
   public Response getVersion() {
      log.trace("Getting version");
      long start = System.currentTimeMillis();
      Response response = Response.status(200).entity(this.manager.getDescriptor()).build();
      log.trace("[{}] Execution time: {}", response.getStatus(), System.currentTimeMillis() - start);
      return response;
   }

   @GET
   @Path("/outputs")
   @Produces({"application/json"})
   public Response getOutputs(@QueryParam("names") List<String> names) throws InterruptedException {
      log.trace("Getting outputs: {}", names);
      long start = System.currentTimeMillis();
      ModelRequestOutput outputReq = new ModelRequestOutput(names.toArray(String[]::new));
      ModelResponse modelResponse = this.manager.execute(outputReq);
      Response response = Response.status(modelResponse.successful ? 200 : 400).entity(modelResponse).build();
      log.trace("[{}] Execution time: {}", response.getStatus(), System.currentTimeMillis() - start);
      return response;
   }

   @GET
   @Path("/status")
   @Produces({"application/json"})
   public Response getStatus() throws InterruptedException {
      log.trace("Getting general status");
      long start = System.currentTimeMillis();

      Response response;
      try {
         ModelResponse modelResponse = this.manager.execute(new ModelRequestStatus());
         response = Response.status(modelResponse.successful ? 200 : 500).entity(modelResponse).build();
      } catch (NullPointerException var5) {
         log.error("Error when attempting to get status", var5);
         response = Response.status(500, "Failed to get status").entity(new ServerException(var5)).build();
      }

      log.trace("[{}] Execution time: {}", response.getStatus(), System.currentTimeMillis() - start);
      return response;
   }

   @GET
   @Path("/lock")
   @Produces({"application/json"})
   public Response lockForEngineUpdate(@QueryParam("state") List<String> states, @QueryParam("timeout") int timeout) throws InterruptedException {
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
