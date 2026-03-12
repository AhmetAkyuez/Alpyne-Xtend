package com.anylogic.alpyne.server.api;

import com.anylogic.alpyne.sim.ModelManager;
import org.glassfish.hk2.utilities.binding.AbstractBinder;

public class ModelManagerBinder extends AbstractBinder {
   ModelManager manager;

   public ModelManagerBinder() {
      this.manager = null;
   }

   public ModelManagerBinder(ModelManager manager) {
      this.manager = manager;
   }

   protected void configure() {
      this.bind(this.manager).to(ModelManager.class);
   }
}
