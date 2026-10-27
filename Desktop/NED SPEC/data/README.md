# Put your part files here

The organizers supplied no sample files, so this project ships **no** parts. Drop the real
ones in here - or drag them onto **Add part files** in the sidebar of the app, which saves
them under `data/uploads/`.

For one part, any of these three file types (in any naming style, in any subfolder):

- **Excel** - the manufacturing record: `.xlsx`, `.xlsm`, `.csv`
- **PDF** - the engineering drawing: text or scanned
- **IGES** - the 3D model: `.igs`, `.iges`

Subfolders are fine (`2280/2280.pdf`, `records/factory_master.csv`, `drawings/3004 rev C.pdf`).
The app discovers every part number it can see and lists them in the dropdown.

Want files to try it on before you have real ones? Generate the synthetic corpus - five
parts that deliberately break our own conventions (French headings, an inch model, a planted
dimension mismatch, a drawing that is only an image, an injection line in a note):

```bash
python scripts/make_test_data.py --out data/demo
python main.py --data data/demo --list
```

They are generated, never committed, and clearly not the organizers' data.
