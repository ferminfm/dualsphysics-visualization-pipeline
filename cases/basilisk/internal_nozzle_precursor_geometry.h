#ifndef INTERNAL_NOZZLE_PRECURSOR_GEOMETRY_H
#define INTERNAL_NOZZLE_PRECURSOR_GEOMETRY_H

#include <math.h>

/*
 * Shared geometry contract for the W2 internal-nozzle precursor family.
 *
 * Coordinates are solver-length units.  The precursor occupies exactly the
 * 2 Dh plenum, 3 Dh smooth contraction and 10 Dh straight rectangular duct.
 * The 2:1 exit has the same area as the historical circular reference with
 * radius 1/12.  This header deliberately contains geometry only; pressure,
 * phase and boundary-condition choices remain explicit in each case source.
 */

#define INTERNAL_NOZZLE_GEOMETRY_SCHEMA "internal_nozzle_w2_geometry_v1"
#define INTERNAL_NOZZLE_GEOMETRY_FINGERPRINT \
  "w2-area-pi-over-144-plenum2dh-contraction3dh-straight10dh-smoothstep-v1"
#define INTERNAL_NOZZLE_OFFICIAL_R (1.0/12.0)
#define INTERNAL_NOZZLE_PLENUM_DH 2.0
#define INTERNAL_NOZZLE_CONTRACTION_DH 3.0
#define INTERNAL_NOZZLE_STRAIGHT_DH 10.0
#define INTERNAL_NOZZLE_INTERNAL_DH 15.0
#define INTERNAL_NOZZLE_PLENUM_SCALE 3.0
#define INTERNAL_NOZZLE_ACCEPTED_FULL_DOMAIN_DH 36.0
#define INTERNAL_NOZZLE_ACCEPTED_FULL_DOMAIN_LEVEL 8

typedef struct {
  double official_r;
  double area;
  double width;
  double height;
  double hydraulic_diameter;
  double plenum_dh;
  double contraction_dh;
  double straight_dh;
  double internal_dh;
  double plenum_scale;
} InternalNozzleGeometry;

static inline double internal_nozzle_minimum (double a, double b) {
  return a < b ? a : b;
}

static inline double internal_nozzle_clamp01 (double value) {
  return value < 0. ? 0. : (value > 1. ? 1. : value);
}

static inline double internal_nozzle_smoothstep (double value) {
  value = internal_nozzle_clamp01(value);
  return value*value*(3. - 2.*value);
}

static inline InternalNozzleGeometry internal_nozzle_w2_geometry (void) {
  InternalNozzleGeometry geometry;
  const double pi_value = 3.141592653589793238462643383279502884;
  geometry.official_r = INTERNAL_NOZZLE_OFFICIAL_R;
  geometry.area = pi_value*geometry.official_r*geometry.official_r;
  geometry.width = sqrt(2.*geometry.area);
  geometry.height = geometry.width/2.;
  geometry.hydraulic_diameter =
    2.*geometry.width*geometry.height/(geometry.width + geometry.height);
  geometry.plenum_dh = INTERNAL_NOZZLE_PLENUM_DH;
  geometry.contraction_dh = INTERNAL_NOZZLE_CONTRACTION_DH;
  geometry.straight_dh = INTERNAL_NOZZLE_STRAIGHT_DH;
  geometry.internal_dh = INTERNAL_NOZZLE_INTERNAL_DH;
  geometry.plenum_scale = INTERNAL_NOZZLE_PLENUM_SCALE;
  return geometry;
}

static inline double internal_nozzle_width_at
  (const InternalNozzleGeometry *geometry, double x)
{
  const double x_dh = x/geometry->hydraulic_diameter;
  if (x_dh <= geometry->plenum_dh)
    return geometry->plenum_scale*geometry->width;
  if (x_dh <= geometry->plenum_dh + geometry->contraction_dh) {
    const double blend = internal_nozzle_smoothstep
      ((x_dh - geometry->plenum_dh)/geometry->contraction_dh);
    return (1. - blend)*geometry->plenum_scale*geometry->width +
      blend*geometry->width;
  }
  return geometry->width;
}

static inline double internal_nozzle_height_at
  (const InternalNozzleGeometry *geometry, double x)
{
  const double x_dh = x/geometry->hydraulic_diameter;
  if (x_dh <= geometry->plenum_dh)
    return geometry->plenum_scale*geometry->height;
  if (x_dh <= geometry->plenum_dh + geometry->contraction_dh) {
    const double blend = internal_nozzle_smoothstep
      ((x_dh - geometry->plenum_dh)/geometry->contraction_dh);
    return (1. - blend)*geometry->plenum_scale*geometry->height +
      blend*geometry->height;
  }
  return geometry->height;
}

static inline double internal_nozzle_internal_phi
  (const InternalNozzleGeometry *geometry, double x, double y, double z)
{
  const double half_width = 0.5*internal_nozzle_width_at(geometry, x);
  const double half_height = 0.5*internal_nozzle_height_at(geometry, x);
  return internal_nozzle_minimum(half_width - fabs(y),
                                 half_height - fabs(z));
}

static inline int internal_nozzle_inside_internal_path
  (const InternalNozzleGeometry *geometry, double x, double y, double z,
   double tolerance)
{
  const double outlet = geometry->internal_dh*geometry->hydraulic_diameter;
  return x >= -tolerance && x <= outlet + tolerance &&
    internal_nozzle_internal_phi(geometry, x, y, z) >= -tolerance;
}

static inline double internal_nozzle_interval_overlap
  (double lower_a, double upper_a, double lower_b, double upper_b)
{
  const double lower = lower_a > lower_b ? lower_a : lower_b;
  const double upper = upper_a < upper_b ? upper_a : upper_b;
  return upper > lower ? upper - lower : 0.;
}

static inline double internal_nozzle_aperture_overlap
  (const InternalNozzleGeometry *geometry, double plane_x,
   double y, double z, double delta)
{
  const double width = internal_nozzle_width_at(geometry, plane_x);
  const double height = internal_nozzle_height_at(geometry, plane_x);
  return internal_nozzle_interval_overlap
    (y - 0.5*delta, y + 0.5*delta, -0.5*width, 0.5*width)*
    internal_nozzle_interval_overlap
    (z - 0.5*delta, z + 0.5*delta, -0.5*height, 0.5*height);
}

static inline double internal_nozzle_accepted_l7_delta_dh (void) {
  return INTERNAL_NOZZLE_ACCEPTED_FULL_DOMAIN_DH/
    (double)(1 << INTERNAL_NOZZLE_ACCEPTED_FULL_DOMAIN_LEVEL);
}

static inline double internal_nozzle_precursor_delta_dh (int maximum_level) {
  return INTERNAL_NOZZLE_INTERNAL_DH/(double)(1 << maximum_level);
}

static inline int internal_nozzle_is_physical_l7_equivalent
  (int maximum_level)
{
  return maximum_level > 0 &&
    internal_nozzle_precursor_delta_dh(maximum_level) <=
    internal_nozzle_accepted_l7_delta_dh() + 1e-14;
}

#endif
