/* Paleta del tablero (guía de visualización, modo claro; validada con
   validate_palette.js). Las series usan los slots categóricos en orden fijo;
   la severidad y la cobertura usan la paleta de estado, siempre con su etiqueta. */
export const SERIE = ["#2a78d6", "#eb6834", "#1baf7a"] as const;
export const ESTADO = { bien: "#0ca30c", aviso: "#fab219", serio: "#ec835a", critico: "#d03b3b", neutro: "#8a8984" };
export const TEXTO_SECUNDARIO = "#52514e";
export const GRILLA = "#e6e5e0";
export const SUPERFICIE = "#ffffff";

export const numero = (n: number) => n.toLocaleString("es-AR");
export const diaCorto = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;

