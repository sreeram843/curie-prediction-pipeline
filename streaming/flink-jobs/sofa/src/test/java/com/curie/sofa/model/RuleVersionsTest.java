package com.curie.sofa.model;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class RuleVersionsTest {
  @Test
  void ordersNineBeforeTen() {
    assertTrue(RuleVersions.compare("0.9.0", "0.10.0") < 0);
    assertTrue(RuleVersions.isNewer("0.10.0", "0.9.0"));
    assertFalse(RuleVersions.isNewer("0.9.0", "0.10.0"));
  }

  @Test
  void equalVersions() {
    assertEquals(0, RuleVersions.compare("0.3.0", "0.3.0"));
    assertTrue(RuleVersions.isSameOrNewer("0.3.0", "0.3.0"));
  }

  @Test
  void rejectsInvalid() {
    assertThrows(IllegalArgumentException.class, () -> RuleVersions.compare("1.2", "1.2.0"));
  }
}
