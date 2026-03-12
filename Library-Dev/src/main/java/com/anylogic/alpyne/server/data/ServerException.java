package com.anylogic.alpyne.server.data;

public class ServerException {
   private String type;
   private String message;

   public ServerException(Exception e) {
      this.setType(e.getClass().getName());
      this.setMessage(e.getMessage());
   }

   public String getType() {
      return this.type;
   }

   public void setType(String type) {
      this.type = type;
   }

   public String getMessage() {
      return this.message;
   }

   public void setMessage(String message) {
      this.message = message;
   }
}
