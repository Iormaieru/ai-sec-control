"""Worker de sincronización con Jira.

Servicio aparte del backend (sin HTTP): consume los eventos que la plataforma
deja en jira_outbox y trae a la plataforma lo que cambia en Jira. Reutiliza
los modelos y la lógica de dominio del backend (paquete `app`), que en la
imagen se copia junto a este paquete.
"""
