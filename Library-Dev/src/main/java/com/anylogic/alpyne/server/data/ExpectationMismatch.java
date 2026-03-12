package com.anylogic.alpyne.server.data;

public class ExpectationMismatch {
   public final Object provided;
   public final Object expected;

   public ExpectationMismatch(Object provided, Object expected) {
      this.provided = provided;
      this.expected = expected;
   }
}
