import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { auditSources } from '../../scripts/check-source-pdfs.mjs';

const root = resolve(fileURLToPath(new URL('../..', import.meta.url)));
const inventory = JSON.parse(await readFile(resolve(root, 'knowledge/source-manifest.json'), 'utf8'));
const demo = JSON.parse(await readFile(resolve(root, 'knowledge/generic-house.json'), 'utf8'));

test('Cuban source inventory excludes unrelated jurisdictions and makes no regulatory claim', () => {
  assert.match(inventory.source_commit, /^[a-f0-9]{40}$/);
  assert.equal(inventory.target_jurisdiction, 'CU');
  assert.equal(inventory.status, 'bibliographic_inventory_only_not_a_ruleset');
  assert.equal(inventory.documents.length, 12);
  assert.equal(new Set(inventory.documents.map((item) => item.file)).size, 12);
  assert.ok(inventory.documents.every((item) => item.runtime_eligible === false &&
    /^[a-f0-9]{64}$/.test(item.sha256) && Number.isSafeInteger(item.pdf_pages) && item.pdf_pages > 0));
  assert.deepEqual(inventory.documents.filter((item) => item.target_use === 'conditional_scope_review')
    .map((item) => item.printed_id), ['NC 598:2009']);
  assert.equal(inventory.documents.find((item) => item.file === 'NC 624.pdf').subject,
    'cctv_intrusion_access_control_equipment');
  assert.equal(inventory.documents.find((item) => item.file === 'Normas de Arquitectura y urbanismo.pdf').jurisdiction,
    'EC-Quito');
  assert.equal(demo.regulatory_status, 'illustrative_not_certified');
  assert.equal(demo.spaces.bathroom.window_ratio, 0.05); // solo un vano ilustrativo; NO umbral de NC 598 §8.1
});

test('all three NC 598 dependencies remain unverified, non-executable third-party leads', () => {
  const leadIds = inventory.external_leads.map((lead) => lead.printed_id_claimed).sort();
  assert.deepEqual(leadIds, ['NC 337:2004', 'NC 391-1:2004', 'NC 391-2:2004']);
  const suppliedUrls = {
    'NC 337:2004': 'https://es.scribd.com/document/839981906/NC-337-a2004-26p-his',
    'NC 391-1:2004': 'https://es.scribd.com/document/726082869/NC-391-1-ACCESIBILIDAD-DE-LAS-PERSONAS-AL-MEDIO-FISICO',
    'NC 391-2:2004': 'https://es.scribd.com/document/726084792/NC-391-2',
  };
  for (const lead of inventory.external_leads) assert.equal(lead.url, suppliedUrls[lead.printed_id_claimed]);
  assert.ok(inventory.documents.every((document) => !leadIds.includes(document.printed_id)));
  for (const lead of inventory.external_leads) {
    assert.equal(new URL(lead.url).hostname, 'es.scribd.com');
    assert.equal(lead.runtime_eligible, false);
    assert.equal(lead.status, 'preview_only_official_edition_and_rights_unverified');
    assert.ok(!('sha256' in lead) && !('pdf_pages' in lead));
    assert.ok(lead.relation.includes('NC 598:2009'));
  }
});

test('source checker detects missing or modified bytes without depending on PDFs in this branch', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'arqgen-source-check-'));
  const bytes = Buffer.from('%PDF-1.7\nfixture only');
  const one = {
    documents: [{ file: 'fixture.pdf', sha256: createHash('sha256').update(bytes).digest('hex') }],
    external_leads: [{ url: inventory.external_leads[0].url, runtime_eligible: false }],
  };
  try {
    assert.deepEqual(await auditSources(directory, one), [{ file: 'fixture.pdf', status: 'missing' }]);
    await writeFile(join(directory, 'fixture.pdf'), bytes);
    assert.deepEqual(await auditSources(directory, one), [{ file: 'fixture.pdf', status: 'matches' }]);
    await writeFile(join(directory, 'fixture.pdf'), Buffer.concat([bytes, Buffer.from('altered')]));
    assert.deepEqual(await auditSources(directory, one), [{ file: 'fixture.pdf', status: 'mismatch' }]);
    await writeFile(join(directory, 'fixture.pdf'), Buffer.from('not a pdf'));
    assert.deepEqual(await auditSources(directory, one), [{ file: 'fixture.pdf', status: 'mismatch' }]);
    await assert.rejects(auditSources(directory, { documents: [{ ...one.documents[0], file: '../outside.pdf' }] }), /inválido/);
  } finally { await rm(directory, { recursive: true, force: true }); }
});
