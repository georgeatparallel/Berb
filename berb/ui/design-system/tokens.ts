/** Apple-inspired design tokens for Berb UI.
 *
 * Based on Apple Human Interface Guidelines:
 * - Light theme as primary
 * - Clean white canvas with subtle warm grays
 * - Typography: SF Pro Display / SF Pro Text system
 * - Berb Blue (#0071E3) as primary accent
 * - 8px grid system
 * - Subtle, layered shadows
 * - Smooth spring animations
 */

// ============================================================================
// COLOR PALETTE
// ============================================================================

/** Berb color palette - Apple-inspired with Berb Blue accent */
export const colors = {
  // Base
  background: '#FFFFFF',
  surface: '#F5F5F7',
  surfaceHover: '#E8E8ED',
  border: '#D2D2D7',
  borderSubtle: '#E5E5EA',

  // Text
  textPrimary: '#1D1D1F',
  textSecondary: '#6E6E73',
  textTertiary: '#86868B',
  textInverse: '#FFFFFF',

  // Accent — Berb Blue (#0071E3)
  accent: '#0071E3',
  accentHover: '#0077ED',
  accentActive: '#0066CC',
  accentLight: '#E1F0FF',
  accentFocus: 'rgba(0, 113, 227, 0.3)',

  // Semantic
  success: '#34C759',
  successLight: '#E8F9ED',
  successBorder: '#28A745',
  warning: '#FF9F0A',
  warningLight: '#FFF5E1',
  warningBorder: '#FF9F0A',
  error: '#FF3B30',
  errorLight: '#FFE5E5',
  errorBorder: '#FF3B30',

  // Stages
  stageComplete: '#34C759',
  stageRunning: '#0071E3',
  stagePending: '#D2D2D7',
  stageError: '#FF3B30',
  stagePaused: '#FF9F0A',

  // Literature
  citationSupporting: '#34C759',
  citationContrasting: '#FF3B30',
  citationMentioning: '#86868B',

  // Code/terminal
  codeBackground: '#1D1D1F',
  codeText: '#FFFFFF',
  codeKeyword: '#AA55FF',
  codeString: '#ACFA5B',
  codeComment: '#86868B',
} as const;

/** Type exports for color palette */
export type ColorName = keyof typeof colors;

// ============================================================================
// TYPOGRAPHY
// ============================================================================

/** SF Pro Display / System font stack */
export const fontFamily = {
  sans: '-apple-system, "SF Pro Display", "Helvetica Neue", Arial, sans-serif',
  mono: '"SF Mono", "Fira Code", "Consolas", "Monaco", monospace',
  serif: '"Georgia", "Times New Roman", serif',
} as const;

/** Typography scale */
export const typography = {
  displayLarge: {
    fontSize: '34px',
    fontWeight: 700,
    letterSpacing: '-0.02em',
    lineHeight: 1.2,
    fontFamily: fontFamily.sans,
  },
  displayMedium: {
    fontSize: '28px',
    fontWeight: 600,
    letterSpacing: '-0.01em',
    lineHeight: 1.3,
    fontFamily: fontFamily.sans,
  },
  displaySmall: {
    fontSize: '22px',
    fontWeight: 600,
    letterSpacing: 0,
    lineHeight: 1.35,
    fontFamily: fontFamily.sans,
  },
  heading: {
    fontSize: '22px',
    fontWeight: 600,
    lineHeight: 1.35,
    fontFamily: fontFamily.sans,
  },
  subheading: {
    fontSize: '17px',
    fontWeight: 600,
    lineHeight: 1.4,
    fontFamily: fontFamily.sans,
  },
  bodyLarge: {
    fontSize: '17px',
    fontWeight: 400,
    lineHeight: 1.65,
    fontFamily: fontFamily.sans,
  },
  body: {
    fontSize: '15px',
    fontWeight: 400,
    lineHeight: 1.65,
    fontFamily: fontFamily.sans,
  },
  bodySmall: {
    fontSize: '13px',
    fontWeight: 400,
    lineHeight: 1.5,
    fontFamily: fontFamily.sans,
  },
  caption: {
    fontSize: '13px',
    fontWeight: 400,
    lineHeight: 1.5,
    color: colors.textSecondary,
    fontFamily: fontFamily.sans,
  },
  label: {
    fontSize: '12px',
    fontWeight: 500,
    letterSpacing: '0.04em',
    textTransform: 'uppercase',
    fontFamily: fontFamily.sans,
  },
  code: {
    fontSize: '14px',
    fontWeight: 400,
    lineHeight: 1.5,
    fontFamily: fontFamily.mono,
  },
} as const;

/** Type exports for typography */
export type TypographyVariant = keyof typeof typography;

// ============================================================================
// SPACING (8px grid)
// ============================================================================

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
  xxxl: 64,
} as const;

export const spacingMap = {
  '0': 0,
  '1': spacing.xs,
  '2': spacing.sm,
  '3': spacing.md,
  '4': spacing.lg,
  '5': spacing.xl,
  '6': spacing.xxl,
  '8': spacing.xxxl,
} as const;

/** Type exports for spacing */
export type SpacingKey = keyof typeof spacingMap;

// ============================================================================
// RADIUS
// ============================================================================

export const radius = {
  sm: 6,
  md: 10,
  lg: 14,
  xl: 20,
  pill: 100,
  full: 9999,
} as const;

/** Type exports for radius */
export type RadiusKey = keyof typeof radius;

// ============================================================================
// SHADOWS
// ============================================================================

export const shadows = {
  sm: '0 1px 2px rgba(0,0,0,0.04)',
  md: '0 2px 8px rgba(0,0,0,0.08)',
  lg: '0 8px 30px rgba(0,0,0,0.12)',
  xl: '0 12px 40px rgba(0,0,0,0.16)',
  focus: `0 0 0 4px ${colors.accentFocus}`,
  inset: 'inset 0 1px 3px rgba(0,0,0,0.06)',
} as const;

/** Type exports for shadows */
export type ShadowKey = keyof typeof shadows;

// ============================================================================
// ANIMATIONS
// ============================================================================

export const animation = {
  fast: '150ms ease-out',
  normal: '300ms cubic-bezier(0.25, 0.1, 0.25, 1)',
  slow: '500ms cubic-bezier(0.25, 0.1, 0.25, 1)',
  spring: '400ms cubic-bezier(0.34, 1.56, 0.64, 1)',
  bounce: '200ms ease-in-out',
} as const;

/** Type exports for animation */
export type AnimationKey = keyof typeof animation;

// ============================================================================
// LAYOUT
// ============================================================================

export const layout = {
  sidebarWidth: 240,
  sidebarWidthCollapsed: 64,
  contextPanelWidth: 320,
  headerHeight: 56,
  bottomBarHeight: 48,
  maxContentWidth: 1280,
  containerPadding: 24,
} as const;

// ============================================================================
// Z-INDEX
// ============================================================================

export const zIndex = {
  dropdown: 1000,
  sticky: 1020,
  fixed: 1030,
  modalBackdrop: 1040,
  modal: 1050,
  popover: 1060,
  tooltip: 1070,
} as const;

// ============================================================================
// ICON SIZES
// ============================================================================

export const iconSize = {
  xs: 12,
  sm: 16,
  md: 20,
  lg: 24,
  xl: 32,
  xxl: 48,
} as const;

// ============================================================================
// BORDER WIDTHS
// ============================================================================

export const borderWidth = {
  hairline: 1,
  sm: 2,
  md: 4,
} as const;

// ============================================================================
// OPACITY
// ============================================================================

export const opacity = {
  0: 0,
  5: 0.05,
  10: 0.1,
  15: 0.15,
  20: 0.2,
  25: 0.25,
  30: 0.3,
  40: 0.4,
  50: 0.5,
  60: 0.6,
  70: 0.7,
  80: 0.8,
  90: 0.9,
  100: 1,
} as const;

// ============================================================================
// EXPORTS
// ============================================================================

/** Complete design token system */
export const designTokens = {
  colors,
  fontFamily,
  typography,
  spacing,
  spacingMap,
  radius,
  shadows,
  animation,
  layout,
  zIndex,
  iconSize,
  borderWidth,
  opacity,
} as const;

export default designTokens;
