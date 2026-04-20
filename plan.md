Basándome en todo lo que hablaron en las dos llamadas y los chats, aquí está exactamente en qué quedaron:

---

**El scope del primer milestone (lo que acordaron con Ben)**

Solo esto, nada más:
- Un correo sale de `bettercrafterorders@gmail.com` hacia Stephen
- El sistema lo lee automáticamente
- Extrae los campos del correo
- Los mete al Word template
- El archivo se guarda automáticamente
- Todo hosteado en el Firebase de ellos

No incluye: ShipStation, PDFs, órdenes custom, otros proveedores, reporte de costos. Todo eso es fase 2 en adelante.

---

**Lo que ya tienes**

- El formato exacto del email de Stephen (te lo mandó Leo)
- El link del Word template en OneDrive
- La cuenta de Gmail: `bettercrafterorders@gmail.com`
- El presupuesto acordado: $200 fixed
- El plazo acordado: 2 días
- Plataforma: Firebase del cliente (tienen 2 apps corriendo ahí)

---

**Lo que te falta conseguir del cliente**

Tres cosas que aún no tienes y sin las cuales no puedes ni empezar:

**1. Acceso a Gmail**
Alguien con acceso a `bettercrafterorders@gmail.com` tiene que completar el flujo de autorización de Google en tu máquina, una sola vez. Pídele a Ben o Leo la contraseña de esa cuenta o que te hagan el flujo ellos mismos.

**2. Acceso a Firebase**
Ellos tienen el proyecto de Firebase donde corren sus 2 apps. Necesitan agregarte como colaborador con rol Editor. Pídele a Ben el Firebase Project ID y que te agregue.

**3. El Word descargado**
El link de OneDrive que te mandó Leo. Necesitas abrirlo, descargarlo, y ver exactamente cuántas columnas tiene y cómo se llaman para construir el template de docxtpl.

---

**Lo que tienes que hacer tú técnicamente**

En este orden exacto:

1. Descargar el Word y mapear las columnas
2. Crear el template de docxtpl basado en ese Word
3. Construir el parser para el email de Stephen (ya tienes el ejemplo, es fácil)
4. Integrar Gmail API con OAuth2 usando las credenciales de `bettercrafterorders@gmail.com`
5. Conectar parser + template + Gmail en una Firebase Function scheduled
6. Guardar el archivo generado en Firebase Storage
7. Configurar Firestore para deduplicación
8. Hacer deploy al proyecto Firebase del cliente
9. Probar con un correo real a Stephen y mostrarle el output a Ben

---

**Lo que tienes que mandarle a Ben ahora mismo**

Esto:

*"Ben, to move forward I need two things: first, please add me as a collaborator on your Firebase project (Editor role) and send me the Project ID. Second, I need access to bettercrafterorders@gmail.com to complete a one-time Google authorization — can you share the credentials or have someone complete that step with me on a quick call?"*

---

¿Quieres que empecemos con el parser y el template mientras esperas el acceso?