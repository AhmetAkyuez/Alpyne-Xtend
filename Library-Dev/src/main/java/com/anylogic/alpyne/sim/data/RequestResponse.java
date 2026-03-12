package com.anylogic.alpyne.sim.data;

public class RequestResponse<T> {
   final boolean isSuccessful;
   final T response;
   final ResponseReason reason;
   final Throwable error;

   public RequestResponse(boolean isSuccessful, T response, ResponseReason reason) {
      this.isSuccessful = isSuccessful;
      this.response = response;
      this.reason = reason;
      this.error = null;
   }

   public RequestResponse(boolean isSuccessful, T response, ResponseReason reason, Throwable error) {
      this.isSuccessful = isSuccessful;
      this.response = response;
      this.reason = reason;
      this.error = error;
   }

   public boolean hasResponse() {
      return this.response != null;
   }

   public boolean isSuccessful() {
      return this.isSuccessful;
   }

   public T getResponse() {
      return this.response;
   }

   public ResponseReason getReason() {
      return this.reason;
   }

   public Throwable getError() {
      return this.error;
   }
}
