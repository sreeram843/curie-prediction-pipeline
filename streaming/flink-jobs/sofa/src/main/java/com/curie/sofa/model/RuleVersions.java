package com.curie.sofa.model;

/** Semantic version compare for rule-bundle activation (CURIE-002). */
public final class RuleVersions {
  private RuleVersions() {}

  /**
   * Compare core major.minor.patch versions.
   *
   * @return negative if a&lt;b, 0 if equal, positive if a&gt;b
   */
  public static int compare(String a, String b) {
    int[] pa = parse(a);
    int[] pb = parse(b);
    for (int i = 0; i < 3; i++) {
      if (pa[i] != pb[i]) {
        return Integer.compare(pa[i], pb[i]);
      }
    }
    return 0;
  }

  public static boolean isNewer(String candidate, String current) {
    if (candidate == null || candidate.isBlank()) {
      return false;
    }
    if (current == null || current.isBlank()) {
      return true;
    }
    return compare(candidate, current) > 0;
  }

  public static boolean isSameOrNewer(String candidate, String current) {
    if (candidate == null || candidate.isBlank()) {
      return false;
    }
    if (current == null || current.isBlank()) {
      return true;
    }
    return compare(candidate, current) >= 0;
  }

  static int[] parse(String version) {
    if (version == null || version.isBlank()) {
      throw new IllegalArgumentException("Invalid semver: " + version);
    }
    String core = version.trim();
    int plus = core.indexOf('+');
    if (plus >= 0) {
      core = core.substring(0, plus);
    }
    int dash = core.indexOf('-');
    if (dash >= 0) {
      core = core.substring(0, dash);
    }
    String[] parts = core.split("\\.");
    if (parts.length != 3) {
      throw new IllegalArgumentException("Invalid semver: " + version);
    }
    int[] out = new int[3];
    for (int i = 0; i < 3; i++) {
      out[i] = Integer.parseInt(parts[i]);
      if (out[i] < 0) {
        throw new IllegalArgumentException("Invalid semver: " + version);
      }
    }
    return out;
  }
}
