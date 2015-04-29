# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in root directory
##############################################################################
from openerp import models, fields, api, exceptions, _


class ProcurementOrder(models.Model):
    _inherit = 'procurement.order'

    level = fields.Integer(string='Level')

    @api.multi
    def make_mo(self):
        production_obj = self.env['mrp.production']
        result = super(ProcurementOrder, self).make_mo()
        procurement = self.browse(result.keys()[0])
        production = production_obj.browse(result.values()[0])
        if procurement.plan:
            production.write({'plan': procurement.plan.id})
        return result

    @api.multi
    def set_main_plan(self):
        procurement_obj = self.env['procurement.order']
        for record in self:
            if record.production_id:
                production = record.production_id
                if production.plan:
                    moves = production.move_lines
                    for move in moves:
                        procurements = procurement_obj.search(
                            [('move_dest_id', '=', move.id)])
                        procurements.write({'plan': production.plan.id})
                        procurements.refresh()
                        procurements.set_main_plan()
                    if record.move_ids:
                        for move in record.move_ids:
                            procurements = procurement_obj.search(
                                [('move_dest_id', '=', move.id)])
                            procurements.write({'plan': production.plan.id})
                            procurements.refresh()
                            procurements.set_main_plan()
        return True

    @api.multi
    def run(self, autocommit=False):
        res = super(ProcurementOrder, self).run(autocommit=autocommit)
        self.set_main_plan()
        return res


class ProcurementPlan(models.Model):
    _inherit = 'procurement.plan'

    product_id = fields.Many2one(
        'product.product', string='Final Product')
    qty_to_produce = fields.Integer(
        string='Quantity to be produced')
    mrp_bom_id = fields.Many2one(
        'mrp.bom', string='MRP BoM')
    production_ids = fields.One2many(
        'mrp.production', 'plan', string='Productions', readonly=True)

    @api.multi
    def button_generate_procurements(self):
        for plan in self:
            if not plan.product_id:
                raise exceptions.Warning(_('Error!: You must enter the final'
                                           ' product'))
            if not plan.qty_to_produce:
                raise exceptions.Warning(_('Error!: You must enter the'
                                           ' quantity to produce'))
            if not plan.mrp_bom_id:
                raise exceptions.Warning(_('Error!: No BoM found'))
            res = []
            plan._generate_procurements(
                plan._calculate_bom_details(plan.mrp_bom_id, res))
        return True

    def _calculate_bom_details(self, bom, res):
        for line in bom.bom_line_ids:
            vals = ({'level': 1,
                     'product': line.product_id,
                     'qty': line.product_qty})
            res.append(vals)
            if line.child_line_ids:
                res = self._calculate_bom_line_details(line.child_line_ids,
                                                       1, res)
        return res

    def _calculate_bom_line_details(self, child_line_ids, level, res):
        level += 1
        for line in child_line_ids:
            vals = ({'level': level,
                     'product': line.product_id,
                     'qty': line.product_qty})
            res.append(vals)
            if line.child_line_ids:
                res = self._calculate_bom_line_details(line.child_line_ids,
                                                       level, res)
        return res

    def _generate_procurements(self, res):
        procurement_obj = self.env['procurement.order']
        if not res:
            return True
        for line in res:
            qty = ((line['qty'] * self.qty_to_produce) /
                   self.mrp_bom_id.product_qty)
            val = procurement_obj.onchange_product_id(line['product'].id)
            vals = {'name': 'Generated from plan',
                    'level': line['level'],
                    'product_id': line['product'].id,
                    'plan': self.id,
                    'main_project_id': self.project_id.id,
                    'product_uos': val['value']['product_uos'],
                    'product_uom': val['value']['product_uom'],
                    'product_qty': qty
                    }
            procurement_obj.create(vals)
        return True

    @api.one
    @api.onchange('product_id')
    def onchange_product_id(self):
        bom_obj = self.env['mrp.bom']
        self.mrp_bom_id = False
        if self.product_id:
            cond = [('product_tmpl_id', '=',
                     self.product_id.product_tmpl_id.id),
                    ('product_id', '=', self.product_id.id)]
            boms = bom_obj.search(cond)
            if not boms:
                cond = [('product_tmpl_id', '=', False),
                        ('product_id', '=', self.product_id.id)]
                boms = bom_obj.search(cond)
            if not boms:
                cond = [('product_tmpl_id', '=',
                         self.product_id.product_tmpl_id.id),
                        ('product_id', '=', False)]
                boms = bom_obj.search(cond)
            if not boms:
                self.product_id = False
                raise exceptions.Warning(_('Error!: No BoM found'))
            self.mrp_bom_id = boms[0].id
