import type { Idioma, RespuestaValor } from "../api/types";

type Opcion = Exclude<RespuestaValor, "PENDIENTE">;

/** Textos del formulario público, en el idioma elegido al enviar la invitación. */
export interface TextosCuestionario {
  locale: string;
  cargando: string;
  errorCarga: string;
  titulo: string;
  saludo: (nombre: string) => string;
  instrucciones: (vence: string) => string;
  alTerminar: [string, string, string];
  sinPendientes: string;
  comoResponder: string;
  evidenciaEsperada: string;
  opciones: Record<Opcion, string>;
  ayudaOpciones: Partial<Record<Opcion, string>>;
  limpiar: string;
  comentario: string;
  progreso: (respondidas: number, total: number) => string;
  cambiosSinGuardar: string;
  guardar: string;
  enviar: string;
  guardado: string;
  errorGuardar: string;
  errorEnviar: string;
  confirmarFaltan: (faltan: number) => string;
  confirmarEnviar: string;
  graciasTitulo: string;
  graciasDetalle: (aplicadas: number, omitidas: number) => string;
}

export const TEXTOS_CUESTIONARIO: Record<Idioma, TextosCuestionario> = {
  es: {
    locale: "es-AR",
    cargando: "Cargando…",
    errorCarga: "No se pudo abrir el cuestionario",
    titulo: "Cuestionario de seguridad de IA",
    saludo: (nombre) => `Hola ${nombre}:`,
    instrucciones: (vence) =>
      "Respondé cada pregunta sobre la solución. Si querés aclarar algo, usá el campo de comentario. " +
      `Podés guardar y volver más tarde con el mismo enlace, que vence el ${vence}.`,
    alTerminar: ["Cuando termines, presioná ", "Enviar respuestas", ". Después de enviar no se pueden modificar."],
    sinPendientes: "No hay preguntas pendientes: el equipo de seguridad ya respondió todo el cuestionario.",
    comoResponder: "¿Cómo responder?",
    evidenciaEsperada: "Evidencia esperada:",
    opciones: { SI: "Sí", NO: "No", NA_ARQ: "No aplica (arquitectura)", NA_FASE: "No aplica (fase)" },
    ayudaOpciones: {
      NA_ARQ: "La solución no tiene ese componente.",
      NA_FASE: "Todavía no corresponde en esta etapa del proyecto.",
    },
    limpiar: "Limpiar",
    comentario: "Comentario (opcional)",
    progreso: (respondidas, total) => `${respondidas} de ${total} respondidas`,
    cambiosSinGuardar: "cambios sin guardar",
    guardar: "Guardar y seguir después",
    enviar: "Enviar respuestas",
    guardado: "Guardado. Podés cerrar esta página y seguir más tarde con el mismo enlace.",
    errorGuardar: "No se pudo guardar",
    errorEnviar: "No se pudieron enviar las respuestas",
    confirmarFaltan: (faltan) =>
      `Quedan ${faltan} pregunta(s) sin responder. Una vez enviado no vas a poder modificarlo. ¿Enviar igual?`,
    confirmarEnviar: "Una vez enviado no vas a poder modificarlo. ¿Enviar las respuestas?",
    graciasTitulo: "¡Gracias! Recibimos tus respuestas",
    graciasDetalle: (aplicadas, omitidas) =>
      `Se registraron ${aplicadas} respuesta(s).` +
      (omitidas > 0 ? ` ${omitidas} ya las había respondido el equipo de seguridad y se mantuvieron.` : ""),
  },
  en: {
    locale: "en-US",
    cargando: "Loading…",
    errorCarga: "The questionnaire could not be opened",
    titulo: "AI security questionnaire",
    saludo: (nombre) => `Hello ${nombre},`,
    instrucciones: (vence) =>
      "Please answer each question about the solution. If you want to clarify something, use the comment field. " +
      `You can save and come back later with the same link, which expires on ${vence}.`,
    alTerminar: ["When you are done, click ", "Submit answers", ". Answers cannot be changed after submitting."],
    sinPendientes: "There are no pending questions: the security team has already answered the whole questionnaire.",
    comoResponder: "How to answer?",
    evidenciaEsperada: "Expected evidence:",
    opciones: { SI: "Yes", NO: "No", NA_ARQ: "N/A (architecture)", NA_FASE: "N/A (phase)" },
    ayudaOpciones: {
      NA_ARQ: "The solution does not have that component.",
      NA_FASE: "Does not apply yet at this stage of the project.",
    },
    limpiar: "Clear",
    comentario: "Comment (optional)",
    progreso: (respondidas, total) => `${respondidas} of ${total} answered`,
    cambiosSinGuardar: "unsaved changes",
    guardar: "Save and continue later",
    enviar: "Submit answers",
    guardado: "Saved. You can close this page and continue later with the same link.",
    errorGuardar: "Could not save",
    errorEnviar: "The answers could not be submitted",
    confirmarFaltan: (faltan) =>
      `${faltan} question(s) are still unanswered. Once submitted you will not be able to change it. Submit anyway?`,
    confirmarEnviar: "Once submitted you will not be able to change it. Submit your answers?",
    graciasTitulo: "Thank you! We received your answers",
    graciasDetalle: (aplicadas, omitidas) =>
      `${aplicadas} answer(s) were recorded.` +
      (omitidas > 0 ? ` ${omitidas} had already been answered by the security team and were kept.` : ""),
  },
};

/** Antes de cargar la invitación no se sabe su idioma: se usa el del navegador. */
export function idiomaDelNavegador(): Idioma {
  return navigator.language.toLowerCase().startsWith("es") ? "es" : "en";
}
