/*
 * Pure platform-glue stubs for the minimal COM-stack node.
 *
 * Every symbol here is plumbing the BSW source references but doesn't
 * affect the Can->CanIf->PduR->Com data path. Nothing in this file
 * fakes a value the stack itself is supposed to produce — see the
 * HARD RULE in PROMPT 2.
 *
 *   Shell_Register
 *     The simulator Can driver registers shell debug commands via the
 *     SHELL_REGISTER macro, which expands to an INITIALIZER calling
 *     this. We don't pump a shell, so accept-and-ignore is correct.
 *
 *   App_IsIgOn
 *     Used by Can.cpp's wakeup poll. For a minimal Tx/Rx run we want
 *     the controller fully awake.
 *
 *   Mcu_IsResetRequested
 *     Read by the upstream main loop to break out of for(;;); our
 *     main.c never calls it. Stubbed for safety so unrelated TUs that
 *     reference it can still link.
 */

#include "Std_Types.h"

void Shell_Register(const void *cmd) {
  (void)cmd;
}

boolean App_IsIgOn(void) {
  return TRUE;
}

boolean Mcu_IsResetRequested(void) {
  return FALSE;
}
